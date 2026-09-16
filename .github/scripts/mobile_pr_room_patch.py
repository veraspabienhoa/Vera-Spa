from pathlib import Path

path = Path('web-v2/src/live-tour-mobile-overrides.css')
css = path.read_text(encoding='utf-8')
marker = '/* MOBILE_PR_BOTTOM_EMPTY_TEXT_MINUS_15_V1 */'
block = '''

/* MOBILE_PR_BOTTOM_EMPTY_TEXT_MINUS_15_V1 */
@media (max-width: 820px) {
  html body .live-tour-page .tour-room-panel .tour-room-grid .tour-room-private-badge {
    top: auto !important;
    bottom: 7px !important;
    scale: 0.8 !important;
    transform-origin: center !important;
  }

  html body .live-tour-page .tour-room-panel .tour-room-grid .tour-room-countdown .tour-room-countdown-empty {
    font-size: min(13.6px, 7.82cqw) !important;
    line-height: 1 !important;
    white-space: nowrap !important;
    overflow-wrap: normal !important;
    word-break: keep-all !important;
  }
}
'''
if marker not in css:
    css += block
path.write_text(css, encoding='utf-8')

assert 'bottom: 7px !important' in css
assert 'font-size: min(13.6px, 7.82cqw) !important' in css
print('MOBILE_PR_BOTTOM_EMPTY_TEXT_MINUS_15=OK')
