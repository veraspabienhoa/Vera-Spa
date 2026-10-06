# FaceGate upload and stored image references

## 07-10-2026: completed uploads can return type 3

A controlled upload returned HTTP 200, UPLOAD.state=100, ERR.no=0 and
UPLOAD.dwfiletype=3. The client rejected that result as invalid_reference
because it applied the persistent registration parser, which accepts type 0,
to upload results. The read-only profile comparison after that test was
unchanged; no profile commit was requested.

The supplied firmware bwlist.js previews getImage with the exact type, index
and position returned by getUploadPercent, then submits those same fields to
setWhitelist. It does not convert type 3 to type 0 before submission.

The adapter therefore validates upload handles separately, allowing known types
0 and 3 with bounded numeric fields. Before a type-3 handle can be committed,
it must also yield a bounded, decodable image. The adapter records a SHA-256 of
its exact RGB pixels and dimensions in the durable upload checkpoint.

After a profile commit, both list and detail reads must identify the same
profile/name/token and agree on a valid persistent type-0 reference. Its image
must have the same pixel fingerprint. The verified persistent reference is
stored in both the mapping and completed journal; the upload handle is never
substituted into attendance mappings. Recovery uses the saved fingerprint and
never replays an upload or profile commit.

Image reads are bounded to 4 MiB and 16 million pixels, use the configured
device session, reject redirects and invalid media, close responses, and occur
outside database transactions. Container metadata may differ; changed decoded
pixels remain unverified.

Tests simulate the upload and persistent references being different, mismatched
images, incorrect identity, invalid/oversized image responses and recovery after
an interrupted commit. The live diagnostic did not test committing a profile or
post-commit image equivalence. That business operation still requires explicit
authorization and production verification; unit/CI success does not establish it.
