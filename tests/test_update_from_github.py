"""start.update_from_github(): a best-effort self-update before launch. Real local git
repos (no network) exercise the actual git commands; no mocking of subprocess internals."""
import subprocess

import pytest

import start


def run_git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                    env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.t",
                         "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.t", "PATH": __import__("os").environ["PATH"]})


def make_origin_and_clone(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    run_git("init", "-q", "-b", "main", cwd=origin)
    (origin / "version.txt").write_text("v1", encoding="utf-8")
    run_git("add", "version.txt", cwd=origin)
    run_git("commit", "-q", "-m", "v1", cwd=origin)
    clone = tmp_path / "clone"
    run_git("clone", "-q", str(origin), str(clone), cwd=tmp_path)
    run_git("config", "user.email", "t@t.t", cwd=clone)
    run_git("config", "user.name", "t", cwd=clone)
    return origin, clone


def test_up_to_date_is_a_quiet_no_op(tmp_path, monkeypatch, capsys):
    origin, clone = make_origin_and_clone(tmp_path)
    monkeypatch.setattr(start, "ROOT", clone)
    start.update_from_github()
    assert (clone / "version.txt").read_text() == "v1"
    assert "Güncelleme kontrol edilemedi" not in capsys.readouterr().out


def test_new_commit_on_origin_is_pulled_and_applied(tmp_path, monkeypatch):
    origin, clone = make_origin_and_clone(tmp_path)
    (origin / "version.txt").write_text("v2", encoding="utf-8")
    run_git("commit", "-q", "-am", "v2", cwd=origin)
    monkeypatch.setattr(start, "ROOT", clone)
    start.update_from_github()
    assert (clone / "version.txt").read_text() == "v2"


def test_local_changes_are_discarded_in_favour_of_github(tmp_path, monkeypatch):
    """Beginner users never hand-edit the app; a stray local change must not block the sync."""
    origin, clone = make_origin_and_clone(tmp_path)
    (origin / "version.txt").write_text("v2", encoding="utf-8")
    run_git("commit", "-q", "-am", "v2", cwd=origin)
    (clone / "version.txt").write_text("local edit, uncommitted", encoding="utf-8")
    monkeypatch.setattr(start, "ROOT", clone)
    start.update_from_github()
    assert (clone / "version.txt").read_text() == "v2"


def test_non_main_branch_is_left_untouched(tmp_path, monkeypatch):
    origin, clone = make_origin_and_clone(tmp_path)
    run_git("checkout", "-q", "-b", "feature", cwd=clone)
    (origin / "version.txt").write_text("v2", encoding="utf-8")
    run_git("commit", "-q", "-am", "v2", cwd=origin)
    monkeypatch.setattr(start, "ROOT", clone)
    start.update_from_github()
    assert (clone / "version.txt").read_text() == "v1"


def test_missing_git_executable_is_a_quiet_no_op(tmp_path, monkeypatch):
    _, clone = make_origin_and_clone(tmp_path)
    monkeypatch.setattr(start, "ROOT", clone)
    monkeypatch.setattr(start.shutil, "which", lambda name: None)
    start.update_from_github()  # must not raise


def test_not_a_git_checkout_is_a_quiet_no_op(tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setattr(start, "ROOT", plain)
    start.update_from_github()  # must not raise


def test_unreachable_remote_warns_but_does_not_raise(tmp_path, monkeypatch, capsys):
    _, clone = make_origin_and_clone(tmp_path)
    run_git("remote", "set-url", "origin", "https://127.0.0.1:1/no-such-repo.git", cwd=clone)
    monkeypatch.setattr(start, "ROOT", clone)
    start.update_from_github()
    assert "Güncelleme kontrol edilemedi" in capsys.readouterr().out
    assert (clone / "version.txt").read_text() == "v1"
