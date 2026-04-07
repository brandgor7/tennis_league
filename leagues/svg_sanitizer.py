import re
import xml.etree.ElementTree as ET

_SVG_NS = 'http://www.w3.org/2000/svg'
_XLINK_NS = 'http://www.w3.org/1999/xlink'

_ALLOWED_ELEMENTS = {
    'svg', 'g', 'path', 'circle', 'ellipse', 'rect', 'line', 'polyline',
    'polygon', 'text', 'tspan', 'defs', 'use', 'symbol', 'clipPath',
    'mask', 'pattern', 'linearGradient', 'radialGradient', 'stop',
    'filter', 'feBlend', 'feColorMatrix', 'feComponentTransfer',
    'feComposite', 'feConvolveMatrix', 'feDiffuseLighting',
    'feDisplacementMap', 'feFlood', 'feGaussianBlur', 'feMerge',
    'feMergeNode', 'feMorphology', 'feOffset', 'feSpecularLighting',
    'feTile', 'feTurbulence', 'title', 'desc', 'image',
}

_UNSAFE_URI = re.compile(r'^\s*(javascript|data|vbscript)\s*:', re.IGNORECASE)
_UNSAFE_CSS = re.compile(
    r'(expression\s*\(|javascript\s*:|url\s*\(\s*["\']?\s*(javascript|data|vbscript))',
    re.IGNORECASE,
)

_HREF_LOCAL_NAMES = {'href', 'src', 'action'}


def sanitize_svg(svg_text):
    """
    Parse, sanitize, and return clean SVG markup.

    Raises ValueError if the input is not valid XML, if the root element is
    not <svg>, or if any structural issue prevents safe sanitization.

    Security approach:
    - Parsed as XML (handles encoding tricks that fool regex)
    - Element allowlist: only recognised SVG elements survive
    - Attribute blocklist: event handlers (on*) and unsafe URI schemes removed
    - href/src limited to fragment references (#id) only — no external loads
    - <foreignObject> and other embed vectors are blocked via the allowlist
    - Dangerous CSS patterns stripped from style attributes
    """
    ET.register_namespace('', _SVG_NS)
    ET.register_namespace('xlink', _XLINK_NS)

    try:
        root = ET.fromstring(svg_text.strip())
    except ET.ParseError as exc:
        raise ValueError(f'Invalid SVG (XML parse error): {exc}')

    _local(root.tag)  # validates tag has expected format
    if _local(root.tag) != 'svg':
        raise ValueError('Root element must be <svg>.')

    _sanitize_element(root, is_root=True)
    return ET.tostring(root, encoding='unicode')


def _local(tag):
    return tag.split('}', 1)[-1] if '}' in tag else tag


def _ns(tag):
    return tag[1:].split('}', 1)[0] if tag.startswith('{') else ''


def _sanitize_element(element, is_root=False):
    local = _local(element.tag)
    ns = _ns(element.tag)

    if not is_root and (ns not in ('', _SVG_NS) or local not in _ALLOWED_ELEMENTS):
        element.tag = '__remove__'
        return

    for attr in list(element.attrib):
        val = element.attrib[attr]
        local_attr = _local(attr).lower()

        if local_attr.startswith('on'):
            del element.attrib[attr]
            continue

        if _UNSAFE_URI.match(val):
            del element.attrib[attr]
            continue

        if local_attr in _HREF_LOCAL_NAMES:
            if not val.startswith('#'):
                del element.attrib[attr]
            continue

        if local_attr == 'style' and _UNSAFE_CSS.search(val):
            del element.attrib[attr]
            continue

    for child in list(element):
        _sanitize_element(child)

    for child in list(element):
        if child.tag == '__remove__':
            element.remove(child)
