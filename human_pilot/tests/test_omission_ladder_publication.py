from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pilot_publish_omission_ladder as publisher
from human_pilot.tests.test_omission_publication import populate,release
from eten_shared.models import Base


def test_research_publication_excludes_holds_and_preserves_pilot():
    data=json.loads(publisher.bank.DEST.read_text());live=publisher.live
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    with Session(engine) as db:
        pilot=release();populate(db,pilot);_,preview=live.publish(db,pilot)
        live.publish(db,pilot,apply=True,preview=preview)
        before=live.snapshot(db)[0];answers=live.assignment_texts(db)
        preview=publisher.publish(db,data)
        assert preview['create']==551 and publisher.snapshot(db)=={}
        audit=publisher.publish(db,data,True,preview)
        assert audit['approved_variants']==551 and audit['held_variants']==34
        assert live.snapshot(db)[0]==before and live.assignment_texts(db)==answers
        expected=publisher.expected_rows(data);assert publisher.snapshot(db)==expected
        assert publisher.publish(db,data)['create']==0
        for w in data['windows']:
            installed={r['condition'] for r in expected.values() if r['source_passage_id']==publisher.PREFIX+w['id']}
            assert installed==set(w['conditions']) and not installed&set(w['held_conditions'])


def test_held_and_failed_candidates_cannot_enter_release():
    data=json.loads(publisher.bank.DEST.read_text())
    bad=deepcopy(data);bad['windows'][0]['conditions']['omission15']['checks']['fluent']='no'
    with pytest.raises(ValueError,match='Unapproved'):publisher.expected_rows(bad)
    bad=deepcopy(data);w=next(w for w in bad['windows'] if w['held_conditions'])
    w['conditions'][next(iter(w['held_conditions']))]=deepcopy(w['conditions']['omission15'])
    with pytest.raises(ValueError,match='Held'):publisher.expected_rows(bad)
