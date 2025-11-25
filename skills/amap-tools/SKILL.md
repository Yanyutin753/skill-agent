---
name: amap-tools
description: "当用户询问旅游攻略、出行规划、景点推荐、美食推荐、酒店住宿、路线导航、天气查询、城市游玩时，必须加载此技能并使用高德地图工具(maps_*)获取实时准确信息，禁止使用网络搜索替代"
license: MIT
allowed-tools: ["maps_poi_search_keyword", "maps_poi_search_nearby", "maps_direction_driving", "maps_direction_transit", "maps_direction_walking", "maps_geo", "maps_regeo", "maps_weather", "maps_district_search", "maps_ip_location"]
---

# 高德地图工具 (AMap Tools)

## 概述

本技能提供高德地图相关服务，包括：
- 🗺️ POI 搜索（景点、餐厅、酒店等）
- 🚗 路线规划（驾车、公交、步行）
- 🌤️ 天气查询
- 📍 地理编码/逆地理编码
- 🏙️ 行政区划查询

## 使用场景

### 🎯 何时使用高德地图工具

当用户询问以下内容时，**必须**使用高德地图工具：

1. **旅游攻略**：生成某城市/景点的旅游攻略
2. **出行规划**：从 A 到 B 怎么走、多长时间
3. **景点推荐**：某地有什么好玩的地方
4. **美食推荐**：某地有什么好吃的餐厅
5. **住宿推荐**：某地有什么酒店
6. **天气查询**：某地天气怎么样
7. **位置查询**：某地在哪里、某坐标是什么地方

## 可用工具

### 1. POI 搜索

#### maps_poi_search_keyword - 关键词搜索
搜索指定城市内的 POI（兴趣点）。

**参数：**
- `keywords`: 搜索关键词（如"火锅"、"酒店"、"景点"）
- `city`: 城市名称（如"北京"、"上海"）
- `types`: POI 类型（可选，如"餐饮"、"住宿"）
- `page_size`: 返回数量（默认 10）

**示例：**
```
搜索北京的火锅店：
keywords="火锅", city="北京"

搜索上海的五星级酒店：
keywords="五星级酒店", city="上海"
```

#### maps_poi_search_nearby - 周边搜索
搜索指定位置周边的 POI。

**参数：**
- `location`: 中心点坐标（经度,纬度）
- `keywords`: 搜索关键词
- `radius`: 搜索半径（米）
- `types`: POI 类型（可选）

### 2. 路线规划

#### maps_direction_driving - 驾车路线
规划驾车路线。

**参数：**
- `origin`: 起点坐标或地址
- `destination`: 终点坐标或地址
- `strategy`: 策略（0-速度优先，1-费用优先，2-距离优先）

#### maps_direction_transit - 公交路线
规划公共交通路线。

**参数：**
- `origin`: 起点坐标
- `destination`: 终点坐标
- `city`: 城市名称
- `strategy`: 策略（0-最快，1-最省钱，2-最少换乘）

#### maps_direction_walking - 步行路线
规划步行路线。

**参数：**
- `origin`: 起点坐标
- `destination`: 终点坐标

### 3. 地理编码

#### maps_geo - 地址转坐标
将地址转换为经纬度坐标。

**参数：**
- `address`: 地址字符串
- `city`: 城市名称（可选，提高精度）

**示例：**
```
address="北京市朝阳区阜通东大街6号"
```

#### maps_regeo - 坐标转地址
将经纬度坐标转换为地址。

**参数：**
- `location`: 坐标（经度,纬度）

### 4. 天气查询

#### maps_weather - 天气信息
查询城市天气。

**参数：**
- `city`: 城市名称或 adcode
- `extensions`: "base"（实况）或 "all"（预报）

**示例：**
```
查询北京实时天气：city="北京", extensions="base"
查询上海天气预报：city="上海", extensions="all"
```

### 5. 行政区划

#### maps_district_search - 区划查询
查询行政区划信息。

**参数：**
- `keywords`: 区划名称
- `subdistrict`: 子级行政区级数（0-3）

### 6. IP 定位

#### maps_ip_location - IP 定位
根据 IP 地址获取位置信息。

**参数：**
- `ip`: IP 地址（可选，默认当前 IP）

## 旅游攻略生成流程

当用户请求生成旅游攻略时，按以下流程操作：

### 步骤 1：查询天气
```
使用 maps_weather 查询目的地天气
- city: 目的地城市
- extensions: "all" (获取预报)
```

### 步骤 2：搜索热门景点
```
使用 maps_poi_search_keyword 搜索景点
- keywords: "景点" 或 "旅游景区"
- city: 目的地城市
- page_size: 10
```

### 步骤 3：搜索美食
```
使用 maps_poi_search_keyword 搜索餐厅
- keywords: "特色美食" 或 "网红餐厅"
- city: 目的地城市
```

### 步骤 4：搜索住宿
```
使用 maps_poi_search_keyword 搜索酒店
- keywords: "酒店" 或 "民宿"
- city: 目的地城市
```

### 步骤 5：规划路线
```
使用 maps_direction_* 规划景点之间的路线
- 根据距离选择驾车/公交/步行
```

### 步骤 6：生成攻略
综合以上信息，生成包含以下内容的攻略：
- 🌤️ 天气概况和穿衣建议
- 🏛️ 推荐景点及简介
- 🍜 美食推荐
- 🏨 住宿推荐
- 🗓️ 行程安排（含交通方式和时间）
- 💡 旅行小贴士

## 示例对话

### 用户：帮我生成一份杭州三日游攻略

**AI 执行流程：**

1. 调用 `maps_weather(city="杭州", extensions="all")` 获取天气
2. 调用 `maps_poi_search_keyword(keywords="景点", city="杭州")` 获取景点
3. 调用 `maps_poi_search_keyword(keywords="特色美食", city="杭州")` 获取美食
4. 调用 `maps_poi_search_keyword(keywords="酒店", city="杭州")` 获取住宿
5. 对主要景点调用 `maps_direction_transit` 规划路线
6. 综合信息生成攻略

### 用户：从北京到上海怎么走最快

**AI 执行流程：**

1. 调用 `maps_geo(address="北京")` 获取北京坐标
2. 调用 `maps_geo(address="上海")` 获取上海坐标
3. 调用 `maps_direction_driving(origin=北京坐标, destination=上海坐标)` 获取驾车路线
4. 返回路线信息（距离、时间、途经点）

## 注意事项

1. **坐标格式**：高德使用 GCJ-02 坐标系，格式为 "经度,纬度"
2. **城市名称**：使用中文城市名，如"北京"、"上海"
3. **搜索精度**：指定城市可提高搜索精度
4. **路线策略**：根据用户需求选择合适的策略
5. **天气预报**：extensions="all" 可获取未来几天的预报

## 参考

更多高德地图 API 详情，请参考：
- [高德开放平台](https://lbs.amap.com/)
- [Web服务 API](https://lbs.amap.com/api/webservice/summary)
