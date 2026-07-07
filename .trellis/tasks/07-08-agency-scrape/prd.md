# 中介站直采（child D · 暂缓 DEFERRED）

> 父任务：`07-08-multi-source-collection`。研究结论见 `../07-08-multi-source-collection/research/agency-antibot.md`。

## 决定：暂缓，不在本轮实现

链家/贝壳/安居客的城市/商圈 ¥/㎡ 数据形状最贴合本系统，但**本环境无法开箱采集**：

1. **缺国内住宅 IP**（根因）：本机出口是机房 IP（OVH 欧洲），所给代理是美国数据中心 IP，对三站全部 000/RST。链家 pg2 起 302、~15 次后整机 IP 被封（`hip.lianjia.com/forbidden`），甚至不给验证码直接 Forbidden；安居客首请求即 58antibot + 网易易盾滑块。
2. **无可用开源库**：唯一直击版块均价的 `jumper2014/lianjia-beike-spider` 已删库(404)，其 fork 全停留 2018–2019、早于现行反爬、实测失效。
3. **ROI 最低、最易碎、高维护**：相对已限流的 creprice，中介站是"更贵更易碎"的备选而非省力替代。

## 重启前置条件

- 稳定的**中国大陆住宅代理池**（非机房 IP）。
- 有了住宅 IP 后，最小可行版：贝壳/链家 `/xiaoqu/` 版块页聚合 + Playwright 真机 + 严格限速（无验证码，只需绕 IP 封禁）；放弃安居客做主源（滑块成本最高）。
- 复用 child A 框架：新增 `BeikeSource(BaseSource)`，能力 `{CITIES, DISTRICTS, PRICE_TIMELINE}`，接入现有 ¥/㎡ 管线。

## Acceptance Criteria

- [ ] （暂缓）待用户提供国内住宅代理池后重新评估并实现最小可行版。
