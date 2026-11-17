"""候选方案对比与事件标记的纯函数。"""


def _should_compare(compare: bool, produced_itinerary: bool, is_edit: bool) -> bool:
    """A second variant is warranted only for a freshly produced plan that was explicitly requested
    for comparison. An interview turn (no plan) or an in-place edit never spawns a variant B."""
    return bool(compare and produced_itinerary and not is_edit)


def _tag_event(event: dict, variant: str | None) -> dict:
    """Tag a stream event with its variant ("A"/"B") for compare mode. Untagged when variant is None,
    so the single-itinerary flow stays byte-for-byte identical for existing clients."""
    if variant:
        return {**event, "variant": variant}
    return event
