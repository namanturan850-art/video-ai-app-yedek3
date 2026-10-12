"""Script engine: harmless JSON shape slips are repaired; anything else gets
one automatic retry before the plain Turkish schema error. No network."""
import json

import pytest

from app.scripts.engine import SecretGuard, YouTubeScriptEngine, fit
from app.scripts.models import ConceptBlueprint, ScriptError, ScriptPlan


def test_fit_repairs_shape_slips_without_inventing_content():
    raw = {'content_type': 'Doku', 'core_topic': 'x' * 3000, 'main_hook': ['Frage', 'Geheimnis'], 'viewer_promise': {'a': 'Antwort'},
           'section_strategy': 'drei Teile', 'key_topics': 'Bermuda', 'visual_opportunities': [{'shot': 'Meer'}] * 40, 'unknown': 1}
    bp = ConceptBlueprint.model_validate(fit(ConceptBlueprint, raw)).model_dump()
    assert len(bp['core_topic']) == 1000 and bp['main_hook'] == 'Frage; Geheimnis' and bp['viewer_promise'] == 'Antwort'
    assert bp['key_topics'] == ['Bermuda'] and len(bp['visual_opportunities']) == 30 and bp['visual_opportunities'][0] == 'Meer'
    plan = ScriptPlan.model_validate(fit(ScriptPlan, {'sections': [{'title': 'T', 'purpose': 'P', 'key_points': 'k', 'target_words': '1200', 'transition': None, 'notes': 'x'}], 'meta': 1})).model_dump()
    assert plan == {'sections': [{'title': 'T', 'purpose': 'P', 'key_points': ['k'], 'target_words': 900, 'transition': ''}]}
    with pytest.raises(Exception):  # missing required content is not invented
        ConceptBlueprint.model_validate(fit(ConceptBlueprint, {'content_type': 'Doku'}))


class Provider:
    def __init__(self, answers):
        self.answers, self.prompts = list(answers), []

    def generate_script(self, prompt):
        self.prompts.append(prompt)
        return self.answers.pop(0)


GOOD = json.dumps({'sections': [{'title': 'A', 'purpose': 'B', 'key_points': ['c'], 'target_words': 500}]})


def test_one_retry_then_success():
    provider = Provider(['{"sections": "kaputt"}', GOOD])
    result = YouTubeScriptEngine(provider, SecretGuard([])).structured('plan', {'x': 1}, 'Plan it.', ScriptPlan, retry=True)
    assert result['sections'][0]['title'] == 'A' and len(provider.prompts) == 2 and 'did not match' in provider.prompts[1]


def test_two_failures_give_the_plain_error():
    provider = Provider(['nicht json', '{"sections": []}'])  # invalid JSON, then a wrong shape
    with pytest.raises(ScriptError) as error:
        YouTubeScriptEngine(provider, SecretGuard([])).structured('plan', {'x': 1}, 'Plan it.', ScriptPlan, retry=True)
    assert error.value.category == 'schema_invalid' and len(provider.prompts) == 2


def test_other_steps_never_retry_on_their_own():
    provider = Provider(['{"sections": "kaputt"}', GOOD])
    with pytest.raises(ScriptError):
        YouTubeScriptEngine(provider, SecretGuard([])).structured('review', {'x': 1}, 'Check.', ScriptPlan)
    assert len(provider.prompts) == 1  # e.g. the visual plan keeps its own confirmed repair flow
