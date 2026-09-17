"""边缘产品不需要的能力占位，避免引用 yolo-demo 专用模块。"""


def delete_gallery_for_events(event_ids, db=None):
    """人员搜索图库清理 — 边缘盒无此功能。"""
    return None
