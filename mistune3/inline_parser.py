import re
from .state import InlineState
from .util import (
    escape,
    escape_url,
    safe_entity,
    unikey,
)
from .helpers import (
    PUNCTUATION,
    HTML_TAGNAME,
    HTML_ATTRIBUTES,
    ESCAPE_CHAR_RE,
    parse_link_label,
    parse_link_text,
    parse_link_href,
    parse_link_title,
)

PAREN_END_RE = re.compile(r'\s*\)')

AUTO_EMAIL = (
    r'''<[a-zA-Z0-9.!#$%&'*+\/=?^_`{|}~-]+@[a-zA-Z0-9]'''
    r'(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
    r'(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*>'
)

INLINE_HTML = (
    r'<' + HTML_TAGNAME + HTML_ATTRIBUTES + r'\s*/?>|'  # open tag
    r'</' + HTML_TAGNAME + r'\s*>|'  # close tag
    r'<!--(?!>|->)(?:(?!--)[\s\S])+?(?<!-)-->|'  # comment
    r'<\?[\s\S]+?\?>|'    # script like <?php?>
    r'<![A-Z][\s\S]+?>|'  # doctype
    r'<!\[CDATA[\s\S]+?\]\]>'  # cdata
)


class InlineParser:
    state_cls = InlineState

    # we only need to find the start pattern of an inline token
    SPECIFICATION = [
        # e.g. \`, \$
        ('escape', r'(?:\\[' + PUNCTUATION + '])+'),

        # `code, ```code
        ('codespan', r'`{1,}'),

        # *w, **w, _w, __w
        ('emphasis', r'\*{1,3}(?=[^\s*])|\b_{1,}(?=[^\s_])'),

        # [link], ![img]
        ('link', r'!?\['),

        # <https://example.com>. regex copied from commonmark.js
        ('auto_link', r'<[A-Za-z][A-Za-z0-9.+-]{1,31}:[^<>\x00-\x20]*>'),
        ('auto_email', AUTO_EMAIL),

        ('inline_html', INLINE_HTML),
    ]

    #: linebreak leaves two spaces at the end of line
    STD_LINEBREAK = r'(?:\\| {2,})\n\s*'

    #: every new line becomes <br>
    HARD_LINEBREAK = r' *\n\s*'


    def __init__(self, renderer, hard_wrap=False):
        self.renderer = renderer

        specification = list(self.SPECIFICATION)
        # lazy add linebreak
        if hard_wrap:
            specification.append(('linebreak', self.HARD_LINEBREAK))
        else:
            specification.append(('linebreak', self.STD_LINEBREAK))
            specification.append(('softbreak', self.HARD_LINEBREAK))

        self.specification = specification
        self.__methods = {
            name: getattr(self, 'parse_' + name) for name, _ in specification
        }
        self._sc = None

    def _compile_sc(self):
        regex = '|'.join('(?P<%s>%s)' % pair for pair in self.specification)
        self._sc = re.compile(regex)

    def register_rule(self, name, pattern, func, before=None):
        if before:
            index = next(i for i, v in enumerate(self.specification) if v[0] == before)
            self.specification.insert(index, (name, pattern))
        else:
            self.specification.append((name, pattern))
        self.__methods[name] = lambda s, pos, state: func(self, s, pos, state)

    def parse_escape(self, m, state):
        text = m.group('escape')
        text = ESCAPE_CHAR_RE.sub(r'\1', text)
        state.tokens.append({
            'type': 'text',
            'raw': safe_entity(text),
        })
        return m.end()

    def parse_link(self, m, state):
        pos = m.end()

        marker = m.group('link')
        is_image = marker[0] == '!'
        if is_image and state.in_image:
            state.tokens.append({'type': 'text', 'raw': marker})
            return pos
        elif not is_image and state.in_link:
            state.tokens.append({'type': 'text', 'raw': marker})
            return pos

        text = None
        label, end_pos = parse_link_label(m.string, pos)
        if label is None:
            text, end_pos = parse_link_text(m.string, pos)
            if text is None:
                return

        if text is None:
            text = label

        if end_pos >= len(m.string):
            if label is None:
                return
        else:
            c = m.string[end_pos]
            if c == '(':
                # standard link [text](<url> "title")
                attrs, pos2 = _parse_std_link(m.string, end_pos + 1)
                if pos2:
                    self._add_link_token(is_image, text, attrs, state)
                    return pos2

            elif c == '[':
                # standard ref link [text][label]
                label2, pos2 = parse_link_label(m.string, end_pos + 1)
                if pos2:
                    end_pos = pos2
                    if label2:
                        label = label2

        if label is None:
            return

        ref_links = state.env['ref_links']
        key = unikey(label)
        attrs = ref_links.get(key)
        if attrs:
            self._add_link_token(is_image, text, attrs, state)
            return end_pos

    def _add_link_token(self, is_image, text, attrs, state):
        new_state = state.copy()
        if is_image:
            new_state.in_image = True
            token = {
                'type': 'image',
                'children': self.render_text(text, new_state),
                'attrs': attrs,
            }
        else:
            new_state.in_link = True
            token = {
                'type': 'link',
                'children': self.render_text(text, new_state),
                'attrs': attrs,
            }
        state.tokens.append(token)

    def parse_auto_link(self, m, state):
        text = m.group('auto_link')
        pos = m.end()
        if state.in_link:
            return self.record_text(pos, text, state)

        text = text[1:-1]
        self._add_auto_link(text, text, state)
        return pos

    def parse_auto_email(self, m, state):
        text = m.group('auto_email')
        pos = m.end()
        if state.in_link:
            return self.record_text(pos, text, state)

        text = text[1:-1]
        url = 'mailto:' + text
        self._add_auto_link(url, text, state)
        return pos

    def _add_auto_link(self, url, text, state):
        children = self.render_tokens([{'type': 'text', 'raw': safe_entity(text)}])
        state.tokens.append({
            'type': 'link',
            'children': children,
            'attrs': {'url': escape_url(url)},
        })

    def parse_emphasis(self, m, state):
        pos = m.end()

        marker = m.group('emphasis')
        if len(marker) > 3:
            if state.in_emphasis or state.in_strong:
                return self.record_text(pos, marker, state)

            _slice = len(marker) - 3
            hole = marker[:_slice]
            marker = marker[_slice:]
        else:
            if len(marker) == 1 and state.in_emphasis:
                return self.record_text(pos, marker, state)
            elif len(marker) == 2 and state.in_strong:
                return self.record_text(pos, marker, state)
            hole = None


        _c = re.escape(marker[0])
        _regex = r'(.*?(?:[^\s' + _c + ']))' + re.escape(marker)
        pattern1 = re.compile(_regex, re.S)
        m1 = pattern1.match(m.string, pos)
        if not m1:
            return self.record_text(pos, marker, state)

        if hole:
            state.tokens.append({'type': 'text', 'raw': safe_entity(hole)})

        new_state = state.copy()
        text = m1.group(1)
        end_pos = m1.end()
        if len(marker) == 1:
            new_state.in_emphasis = True
            children = self.render_text(text, new_state)
            state.tokens.append({'type': 'emphasis', 'children': children})
        elif len(marker) == 2:
            new_state.in_strong = True
            children = self.render_text(text, new_state)
            state.tokens.append({'type': 'strong', 'children': children})
        else:
            new_state.in_emphasis = True
            new_state.in_strong = True

            children = self.render_tokens([{
                'type': 'strong',
                'children': self.render_text(text, new_state)
            }])
            state.tokens.append({
                'type': 'emphasis',
                'children': children,
            })
        return end_pos

    def parse_codespan(self, m, state):
        marker = m.group('codespan')
        # require same marker with same length at end

        pattern = re.compile(r'(.*?(?:[^`]))' + marker + r'(?!`)', re.S)

        pos = m.end()
        m = pattern.match(m.string, pos)
        if m:
            code = m.group(1)
            # Line endings are treated like spaces
            code = code.replace('\n', ' ')
            if len(code.strip()):
                if code.startswith(' ') and code.endswith(' '):
                    code = code[1:-1]
            state.tokens.append({'type': 'codespan', 'raw': escape(code)})
            return m.end()
        return self.record_text(pos, marker, state)

    def parse_linebreak(self, m, state):
        state.tokens.append({'type': 'linebreak'})
        return m.end()

    def parse_softbreak(self, m, state):
        state.tokens.append({'type': 'softbreak'})
        return m.end()

    def parse_inline_html(self, m, state):
        html = m.group('inline_html')
        state.tokens.append({'type': 'inline_html', 'raw': html})
        if html.startswith(('<a ', '<a>')):
            state.in_link = True
        elif html.startswith(('</a ', '</a>')):
            state.in_link = False
        return m.end()

    def parse(self, src, pos, state):
        if not self._sc:
            self._compile_sc()

        while pos < len(src):
            m = self._sc.search(src, pos)
            if not m:
                break

            end_pos = m.start()
            if end_pos > pos:
                hole = safe_entity(src[pos:end_pos])
                state.tokens.append({'type': 'text', 'raw': hole})

            token_type = m.lastgroup
            func = self.__methods[token_type]
            new_pos = func(m, state)
            if not new_pos:
                # move cursor 1 character forward
                pos = end_pos + 1
                hole = safe_entity(src[end_pos:pos])
                state.tokens.append({'type': 'text', 'raw': hole})
            else:
                pos = new_pos

        if pos == 0:
            # special case, just pure text
            state.tokens.append({'type': 'text', 'raw': safe_entity(src)})
        elif pos < len(src):
            state.tokens.append({'type': 'text', 'raw': safe_entity(src[pos:])})
        return state.tokens

    def record_text(self, pos, text, state):
        state.tokens.append({'type': 'text', 'raw': safe_entity(text)})
        return pos

    def render_text(self, s: str, state: InlineState):
        self.parse(s, 0, state)
        return self.render_tokens(state.tokens)

    def render_tokens(self, tokens):
        if self.renderer:
            return self.renderer(tokens)
        return list(tokens)

    def __call__(self, s, refs):
        return self.render_text(s, self.state_cls(refs))


def _parse_std_link(src, pos):
    href, href_pos = parse_link_href(src, pos)
    if href is None:
        return None, None

    title, title_pos = parse_link_title(src, href_pos, len(src))
    next_pos = title_pos or href_pos
    m = PAREN_END_RE.match(src, next_pos)
    if not m:
        return None, None

    href = ESCAPE_CHAR_RE.sub(r'\1', href)
    attrs = {'url': escape_url(href)}
    if title:
        attrs['title'] = safe_entity(title)
    return attrs, m.end()
