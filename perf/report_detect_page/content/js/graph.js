/* Licensed to the Apache Software Foundation (ASF) under one or more
 * contributor license agreements.  See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * ... (Apache License 2.0 声明省略以节省篇幅) ...
 */

$(document).ready(function() {
    // 1. 绑定 UI 交互事件
    $(".click-title").mouseenter(function(e) {
        e.preventDefault();
        this.style.cursor = "pointer";
    }).mousedown(function(event) {
        event.preventDefault();
    });

    // 2. 替换丑陋的 try-catch，改为检查 DOM 元素是否存在再渲染
    if ($('#flotHitsPerSecond').length) refreshHitsPerSecond(true);
    if ($('#flotResponseTimesOverTime').length) refreshResponseTimeOverTime(true);
    if ($('#flotResponseTimesPercentiles').length) refreshResponseTimePercentiles();
    if ($('#flotResponseTimeDistribution').length) refreshResponseTimeDistribution();
    if ($('#flotSyntheticResponseTimeDistribution').length) refreshSyntheticResponseTimeDistribution();
    if ($('#flotActiveThreadsOverTime').length) refreshActiveThreadsOverTime(true);
    if ($('#flotTimesVsThreads').length) refreshTimeVsThreads();
    if ($('#flotBytesThroughputOverTime').length) refreshBytesThroughputOverTime(true);
    if ($('#flotLatenciesOverTime').length) refreshLatenciesOverTime(true);
    if ($('#flotConnectTimeOverTime').length) refreshConnectTimeOverTime(true);
    if ($('#flotResponseTimePercentilesOverTime').length) refreshResponseTimePercentilesOverTime(true);
    if ($('#flotResponseTimeVsRequest').length) refreshResponseTimeVsRequest();
    if ($('#flotLatenciesVsRequest').length) refreshLatenciesVsRequest();
    if ($('#flotCodesPerSecond').length) refreshCodesPerSecond(true);
    if ($('#flotTransactionsPerSecond').length) refreshTransactionsPerSecond(true);
    if ($('#flotTotalTPS').length) refreshTotalTPS(true);
});

/**
 * 提取的公共辅助函数：处理图表的图例克隆和缩放绑定
 * 避免了在每个 refresh 函数中写重复代码
 */
function setupGraphInteractions(mainGraphId, overviewGraphId, choiceContainerId, footerId, infos) {
    var choiceContainer = $(choiceContainerId);
    createLegend(choiceContainer, infos);
    infos.createGraph();
    setGraphZoomable(mainGraphId, overviewGraphId);

    // 克隆颜色块到图例
    $(footerId + ' .legendColorBox > div').each(function(i) {
        $(this).clone().prependTo(choiceContainer.find("li").eq(i));
    });
}

/**
 * 设置空图表时的提示信息
 */
function setEmptyGraph(elementId) {
    $(function() {
        $(elementId).text("No graph series with filter=" + seriesFilter);
    });
}

// ================= 图表配置与数据对象 =================
// (注：为保持代码整洁，此处保留核心结构，省略庞大的 data JSON 数组)

var responseTimePercentilesInfos = {
    data: {"result": {/* ... 原始庞大的 JSON 数据 ... */}},
    getOptions: function() {
        return {
            series: { points: { show: false } },
            legend: { noColumns: 2, show: true, container: '#legendResponseTimePercentiles' },
            xaxis: { tickDecimals: 1, axisLabel: "Percentiles", axisLabelUseCanvas: true, axisLabelFontSizePixels: 12, axisLabelFontFamily: 'Verdana, Arial', axisLabelPadding: 20 },
            yaxis: { axisLabel: "Percentile value in ms", axisLabelUseCanvas: true, axisLabelFontSizePixels: 12, axisLabelFontFamily: 'Verdana, Arial', axisLabelPadding: 20 },
            grid: { hoverable: true },
            tooltip: true,
            tooltipOpts: { content: "%s : %x.2 percentile was %y ms" },
            selection: { mode: "xy" }
        };
    },
    createGraph: function() {
        var data = this.data;
        var dataset = prepareData(data.result.series, $("#choicesResponseTimePercentiles"));
        var options = this.getOptions();
        prepareOptions(options, data);
        $.plot($("#flotResponseTimesPercentiles"), dataset, options);
        $.plot($("#overviewResponseTimesPercentiles"), dataset, prepareOverviewOptions(options));
    }
};

// ... (此处省略其他如 responseTimeDistributionInfos, activeThreadsOverTimeInfos 等对象的定义，结构与原版一致) ...

// ================= 图表刷新函数 =================

function refreshResponseTimePercentiles() {
    var infos = responseTimePercentilesInfos;
    prepareSeries(infos.data);
    if(infos.data.result.series.length == 0) {
        setEmptyGraph("#bodyResponseTimePercentiles");
        return;
    }
    if (isGraph($("#flotResponseTimesPercentiles"))) {
        infos.createGraph();
    } else {
        setupGraphInteractions("#flotResponseTimesPercentiles", "#overviewResponseTimesPercentiles", "#choicesResponseTimePercentiles", "#bodyResponseTimePercentiles", infos);
    }
}

// ... (其他 refresh 函数同样使用 setupGraphInteractions 简化，此处省略) ...

// ================= UI 交互控制 =================

// 使用字典映射替代冗长的 if-else if
var collapseActionMap = {
    "bodyBytesThroughputOverTime": { refresh: refreshBytesThroughputOverTime, fixTs: true, anchor: "#bytesThroughputOverTime" },
    "bodyLatenciesOverTime": { refresh: refreshLatenciesOverTime, fixTs: true, anchor: "#latenciesOverTime" },
    "bodyConnectTimeOverTime": { refresh: refreshConnectTimeOverTime, fixTs: true, anchor: "#connectTimeOverTime" },
    "bodyResponseTimePercentilesOverTime": { refresh: refreshResponseTimePercentilesOverTime, fixTs: true, anchor: "#responseTimePercentilesOverTime" },
    "bodyResponseTimeDistribution": { refresh: refreshResponseTimeDistribution, fixTs: false, anchor: "#responseTimeDistribution" },
    "bodySyntheticResponseTimeDistribution": { refresh: refreshSyntheticResponseTimeDistribution, fixTs: false, anchor: "#syntheticResponseTimeDistribution" },
    "bodyActiveThreadsOverTime": { refresh: refreshActiveThreadsOverTime, fixTs: true, anchor: "#activeThreadsOverTime" },
    "bodyTimeVsThreads": { refresh: refreshTimeVsThreads, fixTs: false, anchor: "#timeVsThreads" },
    "bodyCodesPerSecond": { refresh: refreshCodesPerSecond, fixTs: true, anchor: "#codesPerSecond" },
    "bodyTransactionsPerSecond": { refresh: refreshTransactionsPerSecond, fixTs: true, anchor: "#transactionsPerSecond" },
    "bodyTotalTPS": { refresh: refreshTotalTPS, fixTs: true, anchor: "#totalTPS" },
    "bodyResponseTimeVsRequest": { refresh: refreshResponseTimeVsRequest, fixTs: false, anchor: "#responseTimeVsRequest" },
    "bodyLatenciesVsRequest": { refresh: refreshLatenciesVsRequest, fixTs: false, anchor: "#latencyVsRequest" }
};

function collapse(elem, collapsed) {
    if (collapsed) {
        $(elem).parent().find(".fa-chevron-up").removeClass("fa-chevron-up").addClass("fa-chevron-down");
    } else {
        $(elem).parent().find(".fa-chevron-down").removeClass("fa-chevron-down").addClass("fa-chevron-up");

        var action = collapseActionMap[elem.id];
        if (action) {
            if (isGraph($(elem).find('.flot-chart-content')) == false) {
                action.refresh(action.fixTs);
            }
            document.location.href = action.anchor;
        }
    }
}

function toggleAll(id, checked) {
    var placeholder = document.getElementById(id);
    var cases = $(placeholder).find(':checkbox');
    cases.prop('checked', checked);
    $(cases).parent().children().children().toggleClass("legend-disabled", !checked);

    // 同样使用映射表来触发对应的 refresh 函数
    var toggleMap = {
        "choicesBytesThroughputOverTime": function(){ refreshBytesThroughputOverTime(false); },
        "choicesResponseTimesOverTime": function(){ refreshResponseTimeOverTime(false); },
        "choicesLatenciesOverTime": function(){ refreshLatenciesOverTime(false); },
        "choicesConnectTimeOverTime": function(){ refreshConnectTimeOverTime(false); },
        "choicesResponseTimePercentilesOverTime": function(){ refreshResponseTimePercentilesOverTime(false); },
        "choicesResponseTimePercentiles": function(){ refreshResponseTimePercentiles(); },
        "choicesActiveThreadsOverTime": function(){ refreshActiveThreadsOverTime(false); },
        "choicesTimeVsThreads": function(){ refreshTimeVsThreads(); },
        "choicesHitsPerSecond": function(){ refreshHitsPerSecond(false); },
        "choicesCodesPerSecond": function(){ refreshCodesPerSecond(false); },
        "choicesTransactionsPerSecond": function(){ refreshTransactionsPerSecond(false); },
        "choicesTotalTPS": function(){ refreshTotalTPS(false); },
        "choicesResponseTimeVsRequest": function(){ refreshResponseTimeVsRequest(); },
        "choicesLatencyVsRequest": function(){ refreshLatenciesVsRequest(); }
    };

    if (toggleMap[id]) {
        toggleMap[id]();
    }

    var color = checked ? "black" : "#818181";
    var choiceContainer = $("#" + id);
    if (choiceContainer.length) {
        choiceContainer.find("label").each(function() {
            this.style.color = color;
        });
    }
}