import re
import mistune3 as mistune
from tests import BaseTestCase, normalize_html


DIFF_CASES = {
    'setext_headings_093',
    'html_blocks_191',  # mistune keeps \n

    'images_573', # image can not be in image

    'links_495',  # return early
    'links_496',
}

IGNORE_CASES = {
    'code_spans_341',  # no higher precedence
    'code_spans_342',

    'links_504',  # we don't support link title in (title)

    'links_515',  # please see emphasis issues
    'links_520',  # we return early, no forward/backward
    'links_523',
    'links_524',
    'links_525',
    'links_527',
    'links_529',
    'links_532',
    'links_533',
    'links_535',
    'links_536',
    'links_537',
    'links_563',

    'links_540',  # we don't support this
}

INSANE_CASES = {
    'links_511',  # please use escape
}



class TestCommonMark(BaseTestCase):
    @classmethod
    def ignore_case(cls, n):
        return n in IGNORE_CASES or n in DIFF_CASES or n in INSANE_CASES

    def assert_case(self, n, text, html):
        result = mistune.html(text)
        self.assertEqual(normalize_html(result), normalize_html(html))


TestCommonMark.load_fixtures('commonmark.json')
