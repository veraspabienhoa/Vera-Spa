from pathlib import Path


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'Missing runtime patch anchor: {label}')
    return text.replace(old, new, 1)


page_path = Path('web-v2/src/pages/LiveTourPage.jsx')
page = page_path.read_text(encoding='utf-8')
page = replace_once(
    page,
    "const [appearanceMobile, setAppearanceMobile] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 820px)').matches)",
    "const [appearanceMobile, setAppearanceMobile] = useState(() => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 820px)').matches)",
    'appearance mobile state matchMedia guard',
)
page = replace_once(
    page,
    "  useEffect(() => {\n    const media = window.matchMedia('(max-width: 820px)')\n    const sync = () => setAppearanceMobile(media.matches)\n    sync()\n    media.addEventListener?.('change', sync)\n    return () => media.removeEventListener?.('change', sync)\n  }, [])",
    "  useEffect(() => {\n    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined\n    const media = window.matchMedia('(max-width: 820px)')\n    const sync = () => setAppearanceMobile(media.matches)\n    sync()\n    media.addEventListener?.('change', sync)\n    return () => media.removeEventListener?.('change', sync)\n  }, [])",
    'appearance media effect matchMedia guard',
)
page_path.write_text(page, encoding='utf-8')

lib_path = Path('web-v2/src/lib/liveTourAppearance.js')
lib = lib_path.read_text(encoding='utf-8')
lib = replace_once(
    lib,
    "  key, order, visible: device === 'mobile' ? MOBILE_VISIBLE.has(key) : true, width: 0, font_size: 0,",
    "  key, order, visible: true, width: 0, font_size: 0,",
    'preserve existing mobile visibility by default',
)
lib_path.write_text(lib, encoding='utf-8')

print('LIVE_TOUR_APPEARANCE_RUNTIME_FIX=OK')
