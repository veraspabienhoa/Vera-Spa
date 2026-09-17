from pathlib import Path

path = Path('web-v2/src/pages/LiveTourPage.jsx')
text = path.read_text(encoding='utf-8')
line = "  const appearanceTableColumns = useMemo(() => buildLiveTourTableLayout(columns, activeAppearance, canOperate), [activeAppearance, canOperate, columns])\n"
if line not in text:
    raise SystemExit('appearanceTableColumns anchor missing')
text = text.replace(line, '', 1)

can_operate = "  const canOperate = capability('operate', isAdmin || user?.permissions?.live_tour_operate === true)\n"
active_appearance = "  const activeAppearance = appearanceSettings[appearanceMobile ? 'mobile' : 'desktop']\n"
if can_operate not in text:
    raise SystemExit('canOperate anchor missing')
if active_appearance not in text:
    raise SystemExit('activeAppearance anchor missing')

# Insert only after BOTH dependencies have been initialized. Their relative order
# can differ as LiveTourPage evolves, so choosing the later anchor avoids TDZ
# failures in both browser runtime and the node-based frontend tests.
can_end = text.index(can_operate) + len(can_operate)
active_end = text.index(active_appearance) + len(active_appearance)
insert_at = max(can_end, active_end)
text = text[:insert_at] + line + text[insert_at:]

if not (text.index(can_operate) < text.index(line) and text.index(active_appearance) < text.index(line)):
    raise SystemExit('appearanceTableColumns still precedes a dependency')

path.write_text(text, encoding='utf-8')
print('LIVE_TOUR_APPEARANCE_ORDER=OK')
