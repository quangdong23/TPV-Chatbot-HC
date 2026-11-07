import io
import json
from pathlib import Path

import pytest
from PIL import Image

from app.rag.chemistry import refine_equations


class FakeService:
    def __init__(self, detail, regions=None):
        self.detail = detail
        self.regions = regions if regions is not None else [{'id': 0, 'bbox': [50, 300, 950, 450]}]
        self.calls = 0
        self.page_indices = []
        buffer = io.BytesIO()
        Image.new('RGB', (600, 800), 'white').save(buffer, format='PNG')
        self.image = buffer.getvalue()

    def _render_pages(self, path, indices):
        self.page_indices.extend(indices)
        return [self.image]

    def _encode_image(self, image):
        assert image.width < 600 and image.height < 800
        return self.image

    def _ocr_one(self, image, semaphore, prompt):
        self.calls += 1
        if self.calls == 1:
            return json.dumps({'equations': self.regions})
        return json.dumps(self.detail)


def test_recovers_only_annotation_and_preserves_other_text():
    service = FakeService({'reactants': 'CH2=CH2 + H2', 'products': 'CH3CH3',
                           'above': 'Ni, t°', 'below': '', 'arrow': '→'})
    text = 'Câu hỏi\nCH₂=CH₂ + H₂ → CH₃CH₃\nA. Giữ nguyên đáp án.'
    result = refine_equations(service, Path('test.pdf'), 2, text)
    assert result == 'Câu hỏi\nCH₂=CH₂ + H₂ —[Ni, t°]→ CH₃CH₃\nA. Giữ nguyên đáp án.'
    assert service.page_indices == [2]


@pytest.mark.parametrize('detail,regions', [
    ({'reactants': 'H2 + Cl2', 'products': '3HCl', 'above': 'ánh sáng', 'below': '', 'arrow': '→'}, None),
    ({'reactants': 'H2 + Cl2', 'products': '2HCl', 'above': 'ánh sáng', 'below': '', 'arrow': '⇌'}, None),
    ({'reactants': 'H2 + Cl2', 'products': '2HCl', 'above': '', 'below': '', 'arrow': '→'}, None),
    ({}, None),
    ({}, [{'id': 0, 'bbox': [-1, 10, 50, 60]}]),
    ({}, [{'id': 0, 'bbox': [0, 0, 1000, 1000]}]),
    ({}, [{'id': 99, 'bbox': [50, 300, 950, 450]}]),
])
def test_bad_crop_or_mismatched_formula_retains_original(detail, regions):
    text = 'H₂ + Cl₂ → 2HCl'
    assert refine_equations(FakeService(detail, regions), Path('test.png'), 0, text) == text


def test_no_equation_needs_no_extra_model_call():
    service = FakeService({})
    text = 'A. HCOOCH₃.\nB. CH₃COOH.'
    assert refine_equations(service, Path('test.png'), 0, text) == text
    assert service.calls == 0


def test_annotation_on_both_sides_and_equilibrium():
    service = FakeService({'reactants':'N2 + 3H2','products':'2NH3',
                           'above':'Fe','below':'p, t°','arrow':'⇌'})
    result = refine_equations(service, Path('test.png'), 0, 'N₂ + 3H₂ ⇌ 2NH₃')
    assert result == 'N₂ + 3H₂ —[Fe; dưới: p, t°]⇌ 2NH₃'


def test_locator_failure_does_not_destroy_page():
    class Broken(FakeService):
        def _ocr_one(self, *args): raise RuntimeError('model unavailable')
    text = 'H₂ + Cl₂ → 2HCl'
    assert refine_equations(Broken({}), Path('test.png'), 0, text) == text


@pytest.mark.parametrize('base,mark,expected', [
    ('v', 'bar', 'ν̄'),
    ('ν', 'bar', 'ν̄'),
    ('ν', 'tilde', 'ν̃'),
    ('ν', 'none', 'ν'),
    ('ν', 'unclear', 'ν'),
    ('r', 'dot', 'ν'),
])
def test_symbol_marks_are_read_from_crop_only(base, mark, expected):
    from app.rag.chemistry import refine_symbols
    class SymbolService(FakeService):
        def _encode_image(self, image):
            return self.image
        def _ocr_one(self, image, semaphore, prompt):
            self.calls += 1
            if self.calls == 1:
                return json.dumps({'bbox': [800, 240, 840, 280]})
            return json.dumps({'base': base, 'mark': mark})
    service = SymbolService({})
    result = refine_symbols(service, Path('sample.png'), 0, 'IR: ν = 1750 – 1670 (cm⁻¹).')
    assert result == f'IR: {expected} = 1750 – 1670 (cm⁻¹).'
    assert service.calls == 2


def test_symbol_mark_not_duplicated_and_not_applied_to_other_letters():
    from app.rag.chemistry import refine_symbols
    class Symbols(FakeService):
        def _encode_image(self, image): return self.image
        def _ocr_one(self, image, semaphore, prompt):
            self.calls += 1
            if self.calls % 2:
                return json.dumps({'bbox': [800, 240, 840, 280]})
            return json.dumps({'base': 'ν', 'mark': 'bar'})
    result = refine_symbols(Symbols({}), Path('sample.png'), 0, 'ν̄ = 1; x = 2')
    assert result == 'ν̄ = 1; x = 2'


def test_table_separator_preserves_numbers_and_existing_delimiter():
    from app.rag.chemistry import repair_table_separators
    text = 'Nội dung\n| Chất | Glycine | Glutamic acid | Lysine |\n| pI | 6,0 | 3,2 | 9,7 |\nKết thúc'
    result = repair_table_separators(text)
    assert result == text.replace('\n| pI', '\n| --- | --- | --- | --- |\n| pI')
    assert repair_table_separators(result) == result
    assert repair_table_separators('| a | b |\n| 1 | 2 | 3 |') == '| a | b |\n| 1 | 2 | 3 |'
