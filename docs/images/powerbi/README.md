# Power BI screenshot provenance

Four user-captured screenshots of the validated synthetic Rivaline report, supplied on
2026-10-08. Originals remain in ignored `screenshots-temp/`; no originals were overwritten.

The saved PNGs contain lossless rectangular crops only. No rescaling, recolouring, text
replacement, generative reconstruction or smoothing was applied. Dashboard navigation,
headings, values and labels are retained. PNG re-encoding removes capture metadata and
reduces size. `provenance.json` records input/output SHA-256 hashes, dimensions, byte sizes
and crop rectangles (left/top inclusive, right/bottom exclusive).

Reproduce on Windows, from the repository root with the four original captures available:

```powershell
powershell -NoProfile -File scripts/prepare_powerbi_screenshots.ps1
```

The script uses Windows System.Drawing and verifies every decoded output pixel against the
cropped input. No extra Python imaging dependency is needed. These coordinates are specific
to the supplied captures; inspect new screenshots before changing them.

Some table cells and rows are clipped or scrollable in the original Desktop captures. The
images preserve that viewport and do not claim to expose all records. Open the PBIP to scroll
and inspect full tables. The other two report pages are documented but were not supplied as
screenshots. All business data is fictional.
