from pathlib import Path

path = Path('web-v2/src/pages/LiveTourPage.jsx')
text = path.read_text(encoding='utf-8')
line = "  const appearanceTableColumns = useMemo(() => buildLiveTourTableLayout(columns, activeAppearance, canOperate), [activeAppearance, canOperate, columns])\n"
if line not in text:
    raise SystemExit('appearanceTableColumns anchor missing')
text = text.replace(line, '', 1)
anchor = "  const canOperate = capability('operate', isAdmin || user?.permissions?.live_tour_operate === true)\n"
if anchor not in text:
    raise SystemExit('canOperate anchor missing')
text = text.replace(anchor, anchor + line, 1)
path.write_text(text, encoding='utf-8')
print('LIVE_TOUR_APPEARANCE_ORDER=OK')
