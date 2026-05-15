/*
   Licensed to the Apache Software Foundation (ASF) under one or more
   contributor license agreements.  See the NOTICE file distributed with
   this work for additional information regarding copyright ownership.
   The ASF licenses this file to You under the Apache License, Version 2.0
   (the "License"); you may not use this file except in compliance with
   the License.  You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
*/

/**
 * =====================================================================
 * JMeter Dashboard 核心渲染脚本
 * 负责将测试数据渲染为 HTML 表格和 Flot 图表
 * =====================================================================
 */

// ==================== 1. 全局配置与状态 ====================

/** @type {boolean} 是否仅显示控制器（Controller）数据 */
var showControllersOnly = false;
/** @type {string} 系列过滤正则表达式 */
var seriesFilter = "";
/** @type {boolean} 是否仅过滤采样器（Sampler）系列 */
var filtersOnlySampleSeries = true;

// ==================== 2. 测试数据集中管理 (Data Decoupling) ====================
// 将 JMeter 生成的硬编码数据提取到统一对象中，实现数据与渲染逻辑分离

const DASHBOARD_DATA = {
    requestSummary: { okPercent: 100.0, koPercent: 0.0 },
    apdex: {
        supportsControllersDiscrimination: true,
        overall: { data: [1.0, 500, 1500, "Total"], isController: false },
        titles: ["Apdex", "T (Toleration threshold)", "F (Frustration threshold)", "Label"],
        items: [
            { data: [1.0, 500, 1500, "GET /detect (10 users)"], isController: false },
            { data: [1.0, 500, 1500, "GET /detect (20 users)"], isController: false },
            { data: [1.0, 500, 1500, "GET /detect (50 users)"], isController: false },
            { data: [1.0, 500, 1500, "GET /detect (100 users)"], isController: false }
        ]
    },
    statistics: {
        supportsControllersDiscrimination: true,
        overall: { data: ["Total", 1153222, 0, 0.0, 6.79, 0, 95, 19.0, 21.0, 88.0, 91.0, 4805.09, 15907.48, 577.17], isController: false },
        titles: ["Label", "#Samples", "FAIL", "Error %", "Average", "Min", "Max", "Median", "90th pct", "95th pct", "99th pct", "Transactions/s", "Received", "Sent"],
        items: [
            { data: ["GET /detect (10 users)", 293537, 0, 0.0, 1.88, 0, 81, 2.0, 2.0, 2.0, 3.0, 4894.98, 16205.05, 587.97], isController: false },
            { data: ["GET /detect (20 users)", 288366, 0, 0.0, 3.48, 0, 73, 4.0, 5.0, 5.0, 5.0, 4805.78, 15909.76, 577.26], isController: false },
            { data: ["GET /detect (50 users)", 293612, 0, 0.0, 7.70, 0, 86, 9.0, 10.0, 10.0, 76.35, 4893.04, 16198.65, 587.74], isController: false },
            { data: ["GET /detect (100 users)", 277707, 0, 0.0, 14.47, 0, 95, 19.0, 21.0, 88.0, 91.0, 4626.98, 15317.85, 555.78], isController: false }
        ]
    },
    errors: {
        supportsControllersDiscrimination: false,
        titles: ["Type of error", "Number of errors", "% in errors", "% in all samples"],
        items: []
    },
    top5Errors: {
        supportsControllersDiscrimination: false,
        overall: { data: ["Total", 1153222, 0, "", "", "", "", "", "", "", "", "", ""], isController: false },
        titles: ["Sample", "#Samples", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors"],
        items: [
            { data: [], isController: false }, { data: [], isController: false },
            { data: [], isController: false }, { data: [], isController: false }
        ]
    }
};

// ==================== 3. 图表配置常量 ====================

/** Flot 饼图配置选项 */
const PIE_CHART_OPTIONS = {
    series: {
        pie: {
            show: true,
            radius: 1,
            label: {
                show: true,
                radius: 3 / 4,
                formatter: function(label, series) {
                    return '<div style="font-size:8pt;text-align:center;padding:2px;color:white;">' +
                        label + '<br/>' + Math.round10(series.percent, -2) + '%</div>';
                },
                background: { opacity: 0.5, color: '#000' }
            }
        }
    },
    legend: { show: true }
};

// ==================== 4. 核心渲染函数 ====================

/**
 * 为统计表格添加分类表头（Requests, Executions, Response Times 等）
 * @param {HTMLTableSectionElement} header - 表格的 thead DOM 元素
 */
function summaryTableHeader(header) {
    var $header = $(header);
    var $newRow = $('<tr class="tablesorter-no-sort"></tr>');

    var categories = [
        { text: "Requests", colSpan: 1 },
        { text: "Executions", colSpan: 3 },
        { text: "Response Times (ms)", colSpan: 7 },
        { text: "Throughput", colSpan: 1 },
        { text: "Network (KB/sec)", colSpan: 2 }
    ];

    categories.forEach(function(cat) {
        $newRow.append($('<th>').attr({ 'data-sorter': false, 'colspan': cat.colSpan }).text(cat.text));
    });

    $header.append($newRow);
}

/**
 * 判断数据行是否满足过滤条件
 * @param {Object} item - 单行数据对象
 * @param {Object} info - 表格整体配置信息
 * @param {RegExp|null} regexp - 过滤正则表达式
 * @param {number} seriesIndex - 用于匹配正则的列索引
 * @returns {boolean} 是否应该渲染该行
 */
function shouldRenderItem(item, info, regexp, seriesIndex) {
    if (item.data.length === 0) return false;

    var passFilter = !regexp ||
                     (filtersOnlySampleSeries && !info.supportsControllersDiscrimination) ||
                     regexp.test(item.data[seriesIndex]);

    var passController = !showControllersOnly ||
                         !info.supportsControllersDiscrimination ||
                         item.isController;

    return passFilter && passController;
}

/**
 * 核心表格渲染引擎：根据配置动态生成 HTML 表格并初始化排序
 * @param {string|jQuery} tableSelector - 表格选择器或 jQuery 对象
 * @param {Object} info - 表格数据与配置
 * @param {Function} formatter - 单元格格式化回调 (colIndex, value) => string
 * @param {Array} defaultSorts - tablesorter 默认排序规则
 * @param {number} seriesIndex - 系列过滤索引
 * @param {Function} [headerCreator] - 自定义表头生成器
 */
function createTable(tableSelector, info, formatter, defaultSorts, seriesIndex, headerCreator) {
    var $table = $(tableSelector);
    if ($table.length === 0) {
        console.warn("createTable: 未找到表格元素", tableSelector);
        return;
    }

    var tableRef = $table[0];
    var header = tableRef.createTHead();
    var regexp = seriesFilter ? new RegExp(seriesFilter, 'i') : null;

    // 1. 渲染自定义表头
    if (typeof headerCreator === 'function') {
        headerCreator(header);
    }

    // 2. 渲染主表头 (列名)
    var $headerRow = $('<tr></tr>');
    info.titles.forEach(function(title) {
        $headerRow.append($('<th>').text(title));
    });
    $(header).append($headerRow);

    // 3. 渲染总计行 (Overall)
    if (info.overall && info.overall.data.length > 0) {
        var $overallBody = $('<tbody class="tablesorter-no-sort"></tbody>');
        var $overallRow = $('<tr></tr>');

        info.overall.data.forEach(function(val, idx) {
            var cellText = formatter ? formatter(idx, val) : val;
            $overallRow.append($('<td>').html(cellText));
        });

        $overallBody.append($overallRow);
        $table.append($overallBody);
    }

    // 4. 渲染数据行 (Items)
    var $tBody = $('<tbody></tbody>');
    info.items.forEach(function(item) {
        if (shouldRenderItem(item, info, regexp, seriesIndex)) {
            var $dataRow = $('<tr></tr>');
            item.data.forEach(function(val, idx) {
                var cellText = formatter ? formatter(idx, val) : val;
                $dataRow.append($('<td>').html(cellText));
            });
            $tBody.append($dataRow);
        }
    });
    $table.append($tBody);

    // 5. 激活 tablesorter 插件
    $table.tablesorter({ sortList: defaultSorts });
}

// ==================== 5. 页面初始化入口 ====================

$(document).ready(function() {

    // 配置 tablesorter 全局默认主题
    $.extend($.tablesorter.defaults, {
        theme: 'blue',
        cssInfoBlock: "tablesorter-no-sort",
        widthFixed: true,
        widgets: ['zebra']
    });

    // --- 渲染请求摘要饼图 ---
    var pieDataset = [
        { label: "FAIL", data: DASHBOARD_DATA.requestSummary.koPercent, color: "#FF6347" },
        { label: "PASS", data: DASHBOARD_DATA.requestSummary.okPercent, color: "#9ACD32" }
    ];
    $.plot($("#flot-requests-summary"), pieDataset, PIE_CHART_OPTIONS);

    // --- 渲染 APDEX 表格 ---
    createTable($("#apdexTable"), DASHBOARD_DATA.apdex, function(index, item) {
        if (index === 0) return item.toFixed(3);
        if (index === 1 || index === 2) return formatDuration(item);
        return item;
    }, [[0, 0]], 3);

    // --- 渲染核心统计数据表格 ---
    createTable($("#statisticsTable"), DASHBOARD_DATA.statistics, function(index, item) {
        if (index === 3) return item.toFixed(2) + '%';         // Error %
        if (index >= 4 && index <= 13) return item.toFixed(2); // 时间与吞吐量指标
        return item;
    }, [[0, 0]], 0, summaryTableHeader);

    // --- 渲染错误信息表格 ---
    createTable($("#errorsTable"), DASHBOARD_DATA.errors, function(index, item) {
        if (index === 2 || index === 3) return item.toFixed(2) + '%';
        return item;
    }, [[1, 1]]);

    // --- 渲染前5大错误统计表格 ---
    createTable($("#top5ErrorsBySamplerTable"), DASHBOARD_DATA.top5Errors, function(index, item) {
        return item;
    }, [[0, 0]], 0);

});