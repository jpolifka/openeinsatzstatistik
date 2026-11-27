# -*- coding: utf-8 -*-
"""Protokoll von Handlungen in einer Wehr (`audit_event`, nur anhängbar, ohne Werte), z. B. CSA-Kennzeichnung."""


def audit(con, email, action, kind=None, ref_id=None, detail=None):
    con.execute("INSERT INTO audit_event (email, action, kind, ref_id, detail) VALUES (?, ?, ?, ?, ?)",
                (email or "lokal", action, kind, ref_id, detail))
