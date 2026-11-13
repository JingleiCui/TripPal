from travel_agent.market_cards import cards_from_markdown, market_url


def test_room_cards_preserve_masked_prices_and_room_conditions():
    text = """酒店房型介绍。
## 一、大床房A
![图片](http://p1.meituan.net/room.jpg)
[**大床房A**](http://dpurl.cn/room) 1张大床1.5米 | 15㎡ | 2人入住 **2晚共￥11XX**
🌟 包含早餐，入住前一天可免费取消。
## 二、双床房
[**双床房**](https://dpurl.cn/twin) 2张单人床 **￥6XX起**
"""
    items = cards_from_markdown(text)
    assert len(items) == 2
    assert items[0]["price_text"] == "2晚共￥11XX"
    assert items[1]["price_text"] == "￥6XX起"
    assert items[0]["photo"].startswith("https://")
    assert items[0]["url"] == "https://dpurl.cn/room"
    assert "15㎡" in items[0]["specification"]
    assert "免费取消" in items[0]["details"]
    assert market_url("javascript:alert(1)") is None
    assert cards_from_markdown("## 报价\n[假房型](javascript:alert(1)) **￥99**") == []


def test_unheaded_multiple_room_cards_do_not_render_as_a_chat_dump():
    text = """查到了对应日期的房型。
![房型](http://p1.meituan.net/a.jpg)
[**大床房A**](http://dpurl.cn/a) 1张大床1.5米 | 15㎡ | 2人入住 确认较快 限时免费取消 **2晚共￥11XX**
![房型](http://p1.meituan.net/b.jpg)
[**高级大床房**](http://dpurl.cn/b) 1张大床1.8米 | 16㎡ | 2人入住 确认较快 限时免费取消 **2晚共￥12XX**
其他说明：均价可能变化。
"""
    items = cards_from_markdown(text)
    assert [item["title"] for item in items] == ["大床房A", "高级大床房"]
    assert [item["price_text"] for item in items] == ["2晚共￥11XX", "2晚共￥12XX"]
    assert "15㎡" in items[0]["specification"]
    assert items[1]["photo"] == "https://p1.meituan.net/b.jpg"
