import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const admin = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false },
});

const ALLOWED_ORIGINS = new Set([
  "https://veraspabienhoa.github.io",
  "http://localhost:5173",
  "http://127.0.0.1:5173",
]);

function cors(req: Request) {
  const origin = req.headers.get("origin") || "";
  const allowed = ALLOWED_ORIGINS.has(origin) ? origin : "https://veraspabienhoa.github.io";
  return {
    "Access-Control-Allow-Origin": allowed,
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Vary": "Origin",
    "Content-Type": "application/json; charset=utf-8",
  };
}

function normalize(value: unknown) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .trim()
    .split(/\s+/)
    .join(" ")
    .toLocaleLowerCase("vi");
}

function locked(value: unknown) {
  if (typeof value === "boolean") return value;
  return new Set(["1", "true", "yes", "y", "khóa", "khoa", "locked", "x"])
    .has(String(value ?? "").trim().toLocaleLowerCase("vi"));
}

function employmentStatus(payload: unknown) {
  const source = payload && typeof payload === "object" ? payload as Record<string, unknown> : {};
  return normalize(source["Trạng thái làm việc"] ?? source.employment_status ?? "Đang làm việc");
}

function constantTimeEqual(a: string, b: string) {
  const aa = new TextEncoder().encode(a);
  const bb = new TextEncoder().encode(b);
  const length = Math.max(aa.length, bb.length);
  let difference = aa.length ^ bb.length;
  for (let index = 0; index < length; index += 1) {
    difference |= (aa[index] ?? 0) ^ (bb[index] ?? 0);
  }
  return difference === 0;
}

async function sha256Hex(value: string) {
  const bytes = new TextEncoder().encode(value);
  const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return Array.from(hash).map((item) => item.toString(16).padStart(2, "0")).join("");
}

function randomPassword() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

async function failedAttempt(attemptKey: string, current: Record<string, unknown> | null) {
  const now = Date.now();
  const started = current?.window_started_at ? new Date(String(current.window_started_at)).getTime() : 0;
  const freshWindow = !started || now - started > 15 * 60 * 1000;
  const failures = freshWindow ? 1 : Number(current?.failures || 0) + 1;
  await admin.from("vera_v2_auth_attempt").upsert({
    attempt_key: attemptKey,
    window_started_at: freshWindow ? new Date(now).toISOString() : current?.window_started_at,
    failures,
    updated_at: new Date(now).toISOString(),
  });
  await new Promise((resolve) => setTimeout(resolve, Math.min(1200, 250 + failures * 100)));
}

Deno.serve(async (req: Request) => {
  const headers = cors(req);
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers });
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ message: "Method not allowed" }), { status: 405, headers });
  }

  try {
    const body = await req.json().catch(() => ({}));
    const usernameInput = String(body?.username ?? "").trim();
    const passwordInput = String(body?.password ?? "");
    if (!usernameInput || !passwordInput || usernameInput.length > 120 || passwordInput.length > 256) {
      return new Response(JSON.stringify({ message: "Tên đăng nhập hoặc mật khẩu không hợp lệ." }), { status: 400, headers });
    }

    const usernameKey = normalize(usernameInput);
    const ip = (req.headers.get("x-forwarded-for") || req.headers.get("cf-connecting-ip") || "unknown").split(",")[0].trim();
    const attemptKey = await sha256Hex(`${usernameKey}|${ip}`);
    const { data: attempt } = await admin.from("vera_v2_auth_attempt")
      .select("window_started_at,failures").eq("attempt_key", attemptKey).maybeSingle();
    if (attempt?.window_started_at
      && Date.now() - new Date(attempt.window_started_at).getTime() <= 15 * 60 * 1000
      && Number(attempt.failures || 0) >= 8) {
      return new Response(JSON.stringify({ message: "Đăng nhập tạm khóa 15 phút do thử sai quá nhiều lần." }), { status: 429, headers });
    }

    const { data: employees, error: employeeError } = await admin.from("employees")
      .select("username,password_value,role,full_name,email,login_locked,payload").limit(500);
    if (employeeError) throw employeeError;

    const employee = (employees || []).find((row: Record<string, unknown>) => normalize(row.username) === usernameKey);
    const passwordMatches = employee
      && !locked(employee.login_locked)
      && constantTimeEqual(passwordInput, String(employee.password_value ?? ""));
    if (!passwordMatches) {
      await failedAttempt(attemptKey, attempt);
      const message = employee && locked(employee.login_locked)
        ? "Tài khoản đang bị khóa."
        : "Tên đăng nhập hoặc mật khẩu không đúng.";
      return new Response(JSON.stringify({ message }), { status: 401, headers });
    }

    if (employmentStatus(employee.payload) !== "dang lam viec") {
      return new Response(JSON.stringify({
        message: "Tài khoản đang Tạm thời nghỉ việc hoặc Đã nghỉ việc nên không thể đăng nhập.",
      }), { status: 403, headers });
    }

    const canonicalUsername = String(employee.username);
    const emailHash = await sha256Hex(normalize(canonicalUsername));
    const internalEmail = `vera-${emailHash.slice(0, 32)}@users.veraspa.local`;
    const ephemeralPassword = randomPassword();
    const metadata = {
      employee_username: canonicalUsername,
      full_name: employee.full_name || canonicalUsername,
      role: employee.role || "nhanvien",
    };

    const { data: profile } = await admin.from("vera_v2_user_profile")
      .select("auth_user_id").eq("employee_username", canonicalUsername).maybeSingle();
    const isFirstWebLogin = !profile?.auth_user_id;
    if (isFirstWebLogin) {
      const existingPayload = employee.payload && typeof employee.payload === "object"
        ? employee.payload as Record<string, unknown> : {};
      const { error: passwordGateError } = await admin.from("employees")
        .update({ payload: { ...existingPayload, must_change_password: true } })
        .eq("username", canonicalUsername);
      if (passwordGateError) throw passwordGateError;
    }
    let authUserId = profile?.auth_user_id ? String(profile.auth_user_id) : "";
    if (authUserId) {
      const { error } = await admin.auth.admin.updateUserById(authUserId, {
        password: ephemeralPassword, email_confirm: true, user_metadata: metadata,
      });
      if (error) throw error;
    } else {
      let authUser: { id?: string } | null = null;
      const { data: created, error: createError } = await admin.auth.admin.createUser({
        email: internalEmail, password: ephemeralPassword, email_confirm: true, user_metadata: metadata,
      });
      if (createError) {
        const { data: listed, error: listError } = await admin.auth.admin.listUsers({ page: 1, perPage: 1000 });
        if (listError) throw createError;
        authUser = (listed.users || []).find((user) => String(user.email || "").toLowerCase() === internalEmail.toLowerCase()) || null;
        if (!authUser?.id) throw createError;
        const { error } = await admin.auth.admin.updateUserById(authUser.id, {
          password: ephemeralPassword, email_confirm: true, user_metadata: metadata,
        });
        if (error) throw error;
      } else {
        authUser = created.user;
      }
      authUserId = String(authUser?.id || "");
      if (!authUserId) throw new Error("Auth user was not created");
    }

    const { error: profileError } = await admin.from("vera_v2_user_profile").upsert({
      auth_user_id: authUserId,
      employee_username: canonicalUsername,
      role: String(employee.role || "nhanvien").toLowerCase(),
      is_active: true,
      updated_at: new Date().toISOString(),
    }, { onConflict: "auth_user_id" });
    if (profileError) throw profileError;
    await admin.from("vera_v2_auth_attempt").delete().eq("attempt_key", attemptKey);

    return new Response(JSON.stringify({
      email: internalEmail,
      password: ephemeralPassword,
      employee_username: canonicalUsername,
      full_name: employee.full_name || canonicalUsername,
      role: String(employee.role || "nhanvien").toLowerCase(),
    }), { status: 200, headers });
  } catch (error) {
    console.error("vera-v2-login error", error instanceof Error ? error.message : String(error));
    return new Response(JSON.stringify({ message: "Không thể đăng nhập Web V2 lúc này." }), { status: 500, headers });
  }
});
