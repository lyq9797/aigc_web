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

// 全局过滤与显示控制变量
var showControllersOnly = false;
var seriesFilter = "";
var filtersOnlySampleSeries = true;

/**
 * 为统计表格添加分类表头（如：请求、执行、响应时间等）
 * @param {HTMLTableSectionElement} header - 表格的 thead 元素
 */
function summaryTableHeader(header) {
    var $header = $(header);
    var $newRow = $('<tr class="tablesorter-no-sort"></tr>');

    // 定义分类表头配置
    var headers = [
        { text: "Requests", colSpan: 1 },
        { text: "Executions", colSpan: 3 },
        { text: "Response Times (ms)", colSpan: 7 },
        { text: "Throughput", colSpan: 1 },
        { text: "Network (KB/sec)", colSpan: 2 }
    ];

    // 使用 jQuery 批量追加 th 元素
    $.each(headers, function(index, config) {
        $newRow.append(
            $('<th>')
                .attr('data-sorter', false)
                .attr('colspan', config.colSpan)
                .text(config.text)
        );
    });

    $header.append($newRow);
}

/**
 * 根据配置数据动态创建并填充表格
 * @param {jQuery} table - 表格的 jQuery 对象
 * @param {Object} info - 表格数据配置（包含 titles, items, overall 等）
 * @param {Function} formatter - 单元格数据格式化回调函数
 * @param {Array} defaultSorts - 默认排序规则
 * @param {number} seriesIndex - 用于过滤的系列索引
 * @param {Function} headerCreator - 自定义表头生成回调
 */
function createTable(table, info, formatter, defaultSorts, seriesIndex, headerCreator) {
    var $table = $(table);
    if ($table.length === 0) return; // 防御性检查：确保表格元素存在

    var tableRef = $table[0];
    var header = tableRef.createTHead();

    // 1. 生成自定义表头（如果提供了回调）
    if (headerCreator) {
        headerCreator(header);
    }

    // 2. 生成主表头（列名）
    var $headerRow = $('<tr></tr>');
    for (var i = 0; i < info.titles.length; i++) {
        $headerRow.append($('<th>').text(info.titles[i]));
    }
    $(header).append($headerRow);

    // 3. 生成总计行（Overall body）
    if (info.overall) {
        var $overallBody = $('<tbody class="tablesorter-no-sort"></tbody>');
        var $overallRow = $('<tr></tr>');
        var overallData = info.overall.data;

        for (var j = 0; j < overallData.length; j++) {
            var cellText = formatter ? formatter(j, overallData[j]) : overallData[j];
            $overallRow.append($('<td>').html(cellText));
        }
        $overallBody.append($overallRow);
        $table.append($overallBody);
    }

    // 4. 生成数据行（Regular body）
    var $tBody = $('<tbody></tbody>');
    var regexp = seriesFilter ? new RegExp(seriesFilter, 'i') : null;

    for (var k = 0; k < info.items.length; k++) {
        var item = info.items[k];

        // 复杂的过滤逻辑：处理正则过滤、仅显示采样器、仅显示控制器等
        var passFilter = (!regexp || (filtersOnlySampleSeries && !info.supportsControllersDiscrimination) || regexp.test(item.data[seriesIndex]));
        var passController = (!showControllersOnly || !info.supportsControllersDiscrimination || item.isController);

        if (passFilter && passController && item.data.length > 0) {
            var $dataRow = $('<tr></tr>');
            for (var col = 0; col < item.data.length; col++) {
                var cellVal = formatter ? formatter(col, item.data[col]) : item.data[col];
                $dataRow.append($('<td>').html(cellVal));
            }
            $tBody.append($dataRow);
        }
    }
    $table.append($tBody);

    // 5. 初始化表格排序插件
    $table.tablesorter({ sortList: defaultSorts });
}

// ==================== 页面初始化逻辑 ====================
$(document).ready(function() {

    // 配置 tablesorter 插件的默认选项
    $.extend($.tablesorter.defaults, {
        theme: 'blue',
        cssInfoBlock: "tablesorter-no-sort",
        widthFixed: true,
        widgets: ['zebra']
    });

    // 1. 渲染请求摘要饼图 (Flot Chart)
    var pieData = [
        { label: "FAIL", data: 0.0, color: "#FF6347" },
        { label: "PASS", data: 100.0, color: "#9ACD32" }
    ];

    $.plot($("#flot-requests-summary"), pieData, {
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
    });

    // 2. 渲染 APDEX 表格
    createTable($("#apdexTable"), {
        "supportsControllersDiscrimination": true,
        "overall": {"data": [1.0, 500, 1500, "Total"], "isController": false},
        "titles": ["Apdex", "T (Toleration threshold)", "F (Frustration threshold)", "Label"],
        "items": [
            {"data": [1.0, 500, 1500, "GET /detect (10 users)"], "isController": false},
            {"data": [1.0, 500, 1500, "GET /detect (50 users)"], "isController": false},
            {"data": [1.0, 500, 1500, "GET /detect (20 users)"], "isController": false},
            {"data": [1.0, 500, 1500, "GET /detect (100 users)"], "isController": false}
        ]
    }, function(index, item){
        if (index === 0) return item.toFixed(3);
        if (index === 1 || index === 2) return formatDuration(item);
        return item;
    }, [[0, 0]], 3);

    // 3. 渲染核心统计数据表格
    createTable($("#statisticsTable"), {
        "supportsControllersDiscrimination": true,
        "overall": {"data": ["Total", 1153222, 0, 0.0, 6.79, 0, 95, 19.0, 21.0, 88.0, 91.0, 4805.09, 15907.48, 577.17], "isController": false},
        "titles": ["Label", "#Samples", "FAIL", "Error %", "Average", "Min", "Max", "Median", "90th pct", "95th pct", "99th pct", "Transactions/s", "Received", "Sent"],
        "items": [
            {"data": ["GET /detect (10 users)", 293537, 0, 0.0, 1.88, 0, 81, 2.0, 2.0, 2.0, 3.0, 4894.98, 16205.05, 587.97], "isController": false},
            {"data": ["GET /detect (50 users)", 293612, 0, 0.0, 7.70, 0, 86, 9.0, 10.0, 10.0, 76.35, 4893.04, 16198.65, 587.74], "isController": false},
            {"data": ["GET /detect (20 users)", 288366, 0, 0.0, 3.48, 0, 73, 4.0, 5.0, 5.0, 5.0, 4805.78, 15909.76, 577.26], "isController": false},
            {"data": ["GET /detect (100 users)", 277707, 0, 0.0, 14.47, 0, 95, 19.0, 21.0, 88.0, 91.0, 4626.98, 15317.85, 555.78], "isController": false}
        ]
    }, function(index, item){
        if (index === 3) return item.toFixed(2) + '%'; // 错误率
        if (index >= 4 && index <= 13) return item.toFixed(2); // 时间与吞吐量指标
        return item;
    }, [[0, 0]], 0, summaryTableHeader);

    // 4. 渲染错误信息表格
    createTable($("#errorsTable"), {
        "supportsControllersDiscrimination": false,
        "titles": ["Type of error", "Number of errors", "% in errors", "% in all samples"],
        "items": []
    }, function(index, item){
        if (index === 2 || index === 3) return item.toFixed(2) + '%';
        return item;
    }, [[1, 1]]);

    // 5. 渲染前5大错误统计表格
    createTable($("#top5ErrorsBySamplerTable"), {
        "supportsControllersDiscrimination": false,
        "overall": {"data": ["Total", 1153222, 0, "", "", "", "", "", "", "", "", "", ""], "isController": false},
        "titles": ["Sample", "#Samples", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors"],
        "items": [
            {"data": [], "isController": false}, {"data": [], "isController": false},
            {"data": [], "isController": false}, {"data": [], "isController": false}
        ]
    }, function(index, item){
        return item;
    }, [[0, 0]], 0);

});