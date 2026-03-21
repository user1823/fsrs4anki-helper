import time

from anki.stats import QUEUE_TYPE_NEW, QUEUE_TYPE_PREVIEW, QUEUE_TYPE_SUSPENDED
from anki.utils import ids2str
from aqt import mw
from aqt.utils import tooltip

from ..i18n import t
from ..utils import adr_dr


def save_adr_dr_in_cards(did=None, filter_flag=False, filtered_cids=set()):
    if not mw.col.get_config("fsrs"):
        tooltip(t("enable-fsrs-warning"))
        return None

    start_time = time.time()

    def on_done(future):
        mw.progress.finish()
        cnt = future.result()
        tooltip(f"ADR_DR saved to {cnt} cards ({time.time() - start_time:.2f}s)")
        mw.reset()

    fut = mw.taskman.run_in_background(
        lambda: _save_adr_dr_background(filter_flag, filtered_cids),
        on_done,
    )
    return fut


def _save_adr_dr_background(filter_flag=False, filtered_cids=set()):
    filter_query = f"AND id IN {ids2str(filtered_cids)}" if filter_flag else ""

    cids = mw.col.db.list(f"""
        SELECT id FROM cards
        WHERE queue NOT IN ({QUEUE_TYPE_SUSPENDED}, {QUEUE_TYPE_NEW}, {QUEUE_TYPE_PREVIEW})
        {filter_query}
    """)
    total = len(cids)
    mw.taskman.run_on_main(
        lambda: mw.progress.start(label="Saving ADR_DR…", max=total, immediate=True)
    )

    undo_entry = mw.col.add_custom_undo_entry("Save ADR_DR in cards")
    updated_cards = []
    cnt = 0
    cancelled = False

    for i, cid in enumerate(cids):
        if cancelled:
            break

        card = mw.col.get_card(cid)
        memory_state = card.memory_state
        if memory_state is None:
            continue

        s = memory_state.stability
        d = memory_state.difficulty
        if s is None or d is None:
            continue

        adr = round(float(adr_dr(s, d)), 2)
        card_dr = round(float(card.desired_retention), 2)
        if card_dr != adr:
            card.desired_retention = adr
            updated_cards.append(card)
            cnt += 1

        if i % 500 == 0:
            mw.taskman.run_on_main(
                lambda pi=i: mw.progress.update(
                    label=f"Processed {pi} / {total} cards…",
                    value=pi,
                    max=total,
                )
            )
            if mw.progress.want_cancel():
                cancelled = True

    mw.col.update_cards(updated_cards)
    mw.col.merge_undo_entries(undo_entry)
    return cnt
