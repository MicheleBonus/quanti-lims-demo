"""Tests for block admin routes (create/edit/delete, day number flexibility)."""
import pytest


def test_block_list_route(client):
    resp = client.get("/admin/blocks")
    assert resp.status_code == 200


def test_block_edit_updates_max_days(client, db):
    from models import Block
    block = Block.query.first()
    assert block is not None
    resp = client.post(f"/admin/blocks/{block.id}/edit",
                       data={"name": block.name, "code": block.code, "max_days": "6"},
                       follow_redirects=True)
    assert resp.status_code == 200
    db.session.expire(block)
    assert block.max_days == 6


def test_block_delete_without_practical_days(client, db):
    """Can delete a block with no linked practical days."""
    from models import Block
    block = Block(code="ZZ", name="TestDeleteBlock")
    db.session.add(block)
    db.session.commit()
    resp = client.post(f"/admin/blocks/{block.id}/delete", follow_redirects=True)
    assert resp.status_code == 200  # succeeds — no linked days
