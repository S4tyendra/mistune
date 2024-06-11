import re
from typing import TYPE_CHECKING, Match

if TYPE_CHECKING:
    from ..block_parser import BlockParser
    from ..core import BaseRenderer, BlockState, InlineState, Parser
    from ..inline_parser import InlineParser
    from ..markdown import Markdown

__all__ = ['mermaid']

MERMAID_BLOCK_PATTERN = re.compile(r'^```mermaid\n([\s\S]+?)\n```', re.M)

def parse_mermaid_block(
    block: "BlockParser", m: Match[str], state: "BlockState"
) -> int:
    text = m.group(1)
    token = {'type': 'mermaid_block', 'text': text}
    state.append_token(token)
    return m.end()

def render_mermaid_block(renderer: "BaseRenderer", text: str) -> str:
    return f'<div class="mermaid">\n{text}\n</div>\n'

def mermaid(md: "Markdown") -> None:
    """A mistune plugin to support mermaid diagrams.
    
    This will convert a mermaid code block to a div with the mermaid class.
    
    .. code-block:: text

        ```mermaid
        graph LR
            A --1--> B
            B --2--> C
            C --3--> D
            D --4--> E
            E --5--> F
            F --6--> A
            style A fill:#f9f,stroke:#333,stroke-width:2px
            style B fill:#f9f,stroke:#333,stroke-width:2px
            style C fill:#f9f,stroke:#333,stroke-width:2px
            style D fill:#f9f,stroke:#333,stroke-width:2px
            style E fill:#f9f,stroke:#333,stroke-width:2px
            style F fill:#f9f,stroke:#333,stroke-width:2px
        ```

    :param md: Markdown instance
    """
    md.block.register('mermaid_block', MERMAID_BLOCK_PATTERN, parse_mermaid_block)
    if md.renderer and md.renderer.NAME == 'html':
        md.renderer.register('mermaid_block', render_mermaid_block)
