"""Read JSX ignoring customization metadata, retaining business expressions."""
import re

def read_ui_source(path):
    source = path.read_text(encoding='utf-8')
    # Include the statically imported view components when checking page invariants.
    if path.name == 'LiveTourPage.jsx':
        for name in re.findall(r"import \w+ from '../components/(LiveTour(?:Board|\w+Panel))'", source):
            component = (path.parent.parent / 'components' / f'{name}.jsx').read_text(encoding='utf-8')
            source = re.sub(r'<' + name + r'\b[^\n]*?/>', lambda _: component, source, count=1)
    source = re.sub(r' data-ui-label-default="[^"]*"', '', source)
    source = re.sub(r' data-ui-key="u-[a-z0-9-]+"', '', source)
    source = re.sub(r'<UiCustomText\s+uiKey="[^"]+">(.*?)</UiCustomText>', r'\1', source, flags=re.S)
    source = source.replace('<UiToolbar', '<div').replace('</UiToolbar>', '</div>')
    return source
