import sys
M={
"M1 close_expired guard weakened (only COMPLETED skipped)":("review/services.py","    if frame.state != FrameReview.State.IN_REVIEW:\n        # The frame moved on","    if frame.state == FrameReview.State.COMPLETED:\n        # The frame moved on"),
"M2 idempotent 200 also for a live lease":("review/issue_service.py","        and lease.closed_at is not None\n        and frame.state in _PAST_REVIEW_STATES","        and frame.state in _PAST_REVIEW_STATES"),
"M3 idempotent 200 ignores undecided issues":("review/issue_service.py","        and frame.state in _PAST_REVIEW_STATES\n        and not decision_source.undecided_issue_ids(frame)\n","        and frame.state in _PAST_REVIEW_STATES\n"),
"M4 verify may downgrade a COMPLETED frame":("review/rework_service.py","    if frame.state == FrameReview.State.COMPLETED:\n        return\n    if decision_source","    if decision_source"),
"M5 verify no longer closes the live lease":("review/rework_service.py","        Lease.objects.filter(frame_review=frame, closed_at__isnull=True).update(\n            closed_at=timezone.now()\n        )\n","        pass\n"),
"M6 renew no longer notices moved-on frame":("review/services.py","    elif lease.closed_at is None:\n        _close_if_frame_moved_on(lease, now)\n","    elif False:\n        pass\n"),
"M7 complete hook removed":("review/issue_service.py","    if decision_source.frame_reworks_all_resolved(frame):\n        frame.state = FrameReview.State.AWAITING_FOLLOWUP\n","    if False:\n        frame.state = FrameReview.State.AWAITING_FOLLOWUP\n"),
"M8 escalated counted as undecided":("review/decision_source.py","        .exclude(state=Issue.State.ESCALATED)\n        .exclude(review_decisions__isnull=False)\n        .values_list","        .exclude(review_decisions__isnull=False)\n        .values_list"),
"M9 completion audit written on every retry":("review/issue_service.py","    ).exists():\n        return\n    append_audit_event(\n        actor=user,\n        action=\"frame.complete\",","    ).exists() and False:\n        return\n    append_audit_event(\n        actor=user,\n        action=\"frame.complete\","),
"M10 claim ignores moved-on live lease (resumes it)":("review/services.py","        elif _close_if_frame_moved_on(lease, now):\n            continue\n","        elif False:\n            continue\n"),
}
name=sys.argv[1]; f,a,b=M[name]
s=open(f).read(); assert a in s,(name); open(f,'w').write(s.replace(a,b,1))
