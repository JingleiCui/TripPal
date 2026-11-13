"""Small source-backed Beijing reference catalogue, not live availability data."""

CATALOGUE = {
    "颐和园": {
        "description": "以万寿山、昆明湖为主体的历史园林，可结合园林建筑与湖区安排参观。",
        "guide_url": "https://yllhj.beijing.gov.cn/ggfw/bjsggml/lsmy/lsmy2/202206/t20220620_2746555.shtml",
        "booking_url": "https://www.summerpalace.net.cn/visit.html",
    },
    "香山公园": {
        "description": "北京西郊具有山林特色的历史园林；具体园内路线、天气和临时开放情况需另行核实。",
        "guide_url": "https://xiangshanpark.com/cn/",
        "booking_url": "https://pc.xiangshantickets.com/index.html",
    },
    "奥林匹克森林公园": {
        "description": "北京中轴线北端的城市公园，南园包含山水、湿地等景观，适合安排公园休闲。",
        "guide_url": "https://yllhj.beijing.gov.cn/ggfw/bjsggml/zhgy/cyq/202206/t20220614_2740317.shtml",
    },
}


def enrich(place):
    reference = CATALOGUE.get(place["name"])
    if reference and "公园" in str(place.get("category", "")):
        return {
            **place,
            **reference,
            "guide_checked_at": "2026-11-12",
            "guide_scope": "静态介绍与官方入口，不证明指定日期开放、库存或价格",
        }
    return place
