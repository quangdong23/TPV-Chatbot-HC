import json
from types import SimpleNamespace

import pytest

from app.documents import ocr_formatting as formatting
from app.core.config import Settings


@pytest.mark.parametrize('phrases', [
    ['BÁO CÁO', 'Fe³⁺', '0,25 mL'],
    ['Không có trong văn bản', 'Fe³⁺ + 3OH⁻ → Fe(OH)₃'],
    ['BÁO CÁO', 'BÁO CÁO\nSố liệu', 'BÁO CÁO'],
    [None, 123, '', ' ', '**BÁO CÁO**', '| A | B |'],
])
def test_formatting_cannot_change_characters(phrases):
    text = 'BÁO CÁO\nSố liệu: 0,25 mL.\nFe³⁺ + 3OH⁻ → Fe(OH)₃\n| A | B |'
    result = formatting.apply_bold(text, phrases)
    assert result.replace('**', '') == text


def test_unique_spans_and_repeated_words():
    text = 'BÁO CÁO\nHóa chất 1; Hóa chất 2. Fe³⁺'
    assert formatting.apply_bold(text, ['BÁO CÁO', 'Hóa chất', 'Fe³⁺']) == (
        '**BÁO CÁO**\nHóa chất 1; Hóa chất 2. **Fe³⁺**')
    assert formatting.apply_bold('Hóa chất', ['chất', 'Hóa chất']) == 'Hóa **chất**'
    assert formatting.apply_bold('báo cáo', ['báo c']) == 'báo cáo'
    assert formatting.apply_bold('**Đậm sẵn**', ['Đậm sẵn']) == '**Đậm sẵn**'


@pytest.mark.parametrize('response', ['invalid json', '{"bold": "BÁO CÁO"}', '{"bold":["TỰ SỬA CHỮ"]}', '[]'])
def test_bad_model_output_preserves_page(monkeypatch, response):
    service = SimpleNamespace(settings=Settings(_env_file=None), _render_pages=lambda *args: [b'image'])
    monkeypatch.setattr(formatting.OCRService, '_ocr_one', lambda *args: response)
    assert formatting.preserve_bold(service, None, 0, 'BÁO CÁO') == 'BÁO CÁO'


def test_style_call_is_separate_and_bounded(monkeypatch):
    cfg = Settings(_env_file=None, ocr_timeout=180, ocr_max_retries=3)
    service = SimpleNamespace(settings=cfg, _render_pages=lambda *args: [b'image'])
    def read(self, image, semaphore, prompt):
        assert self.settings.ocr_timeout == 30
        assert self.settings.ocr_max_retries == 1
        assert json.loads(prompt.removeprefix(formatting.BOLD_PROMPT)) == 'BÁO CÁO\nFe³⁺'
        return '{"bold": ["BÁO CÁO"]}'
    monkeypatch.setattr(formatting.OCRService, '_ocr_one', read)
    assert formatting.preserve_bold(service, None, 0, 'BÁO CÁO\nFe³⁺') == '**BÁO CÁO**\nFe³⁺'
    assert cfg.ocr_timeout == 180
    assert cfg.ocr_max_retries == 3


def test_timeout_keeps_existing_text(monkeypatch):
    service = SimpleNamespace(settings=Settings(_env_file=None), _render_pages=lambda *args: [b'image'])
    def fail(*args):
        raise TimeoutError('model unavailable')
    monkeypatch.setattr(formatting.OCRService, '_ocr_one', fail)
    assert formatting.preserve_bold(service, None, 0, 'C₂H₄O₂') == 'C₂H₄O₂'
