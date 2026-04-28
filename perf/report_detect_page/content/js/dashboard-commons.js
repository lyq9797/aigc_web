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

// 时间常量定义（毫秒）
var DAY_MS   = 86400000;
var HOUR_MS  = 3600000;
var MINUTE_MS = 60000;

/**
 * 修复 JavaScript 原生 Math.round 处理浮点数精度丢失的问题
 * 来源: MDN Web Docs
 */
(function() {
  function decimalAdjust(type, value, exp) {
    if (typeof exp === 'undefined' || +exp === 0) {
      return Math[type](value);
    }
    value = +value;
    exp = +exp;
    if (isNaN(value) || !(typeof exp === 'number' && exp % 1 === 0)) {
      return NaN;
    }
    value = value.toString().split('e');
    value = Math[type](+(value[0] + 'e' + (value[1] ? (+value[1] - exp) : -exp)));
    value = value.toString().split('e');
    return +(value[0] + 'e' + (value[1] ? (+value[1] + exp) : exp));
  }

  if (!Math.round10) {
    Math.round10 = function(value, exp) { return decimalAdjust('round', value, exp); };
  }
  if (!Math.floor10) {
    Math.floor10 = function(value, exp) { return decimalAdjust('floor', value, exp); };
  }
  if (!Math.ceil10) {
    Math.ceil10 = function(value, exp) { return decimalAdjust('ceil', value, exp); };
  }
})();

/**
 * 为数值添加单位后缀
 */
function formatUnit(value, unit, spaced){
    return spaced ? value + " " + unit : value + unit;
}

/**
 * 将毫秒数格式化为可读的时间字符串 (如: "45 min 20 sec 100 ms")
 */
function formatDuration(duration, spaced) {
    if ($.type(duration) === "string") return duration;

    var days = Math.floor(duration / DAY_MS);
    duration %= DAY_MS; // 修复了原代码中 8640000 少一个 0 的 Bug

    var hours = Math.floor(duration / HOUR_MS);
    duration %= HOUR_MS;

    var minutes = Math.floor(duration / MINUTE_MS);
    duration %= MINUTE_MS;

    var seconds = Math.floor(duration / 1000);
    duration %= 1000;

    var formatArray = [];
    if (days > 0) formatArray.push(formatUnit(days, " day(s)", spaced));
    if (hours > 0) formatArray.push(formatUnit(hours, " hour(s)", spaced));
    if (minutes > 0) formatArray.push(formatUnit(minutes," min", spaced));
    if (seconds > 0) formatArray.push(formatUnit(seconds, " sec", spaced));
    if (duration > 0) formatArray.push(formatUnit(duration, " ms", spaced));

    return formatArray.join(" ");
}

// 获取时间轴标签
function getElapsedTimeLabel(granularity) {
    return "Elapsed Time (granularity: " + formatDuration(granularity) + ")";
}

// 根据粒度获取时间格式化字符串
function getTimeFormat(granularity) {
    if (granularity >= DAY_MS) return "%y/%m/%d";
    if (granularity >= HOUR_MS) return "%m/%d %H";
    if (granularity >= MINUTE_MS) return "%d %H:%M";
    return "%H:%M:%S";
}

function getConnectTimeLabel(granularity) {
    return "Connect Time (granularity: " + formatDuration(granularity) + ")";
}

// 安全获取对象深层属性
function getProperty(key, obj) {
    return key.split('.').reduce(function(prop, subprop){
        return prop && prop[subprop];
    }, obj);
}

// 移除字符串首尾引号
function unquote(str, quoteChar) {
    quoteChar = quoteChar || '"';
    if (str.length > 0 && str[0] === quoteChar && str[str.length - 1] === quoteChar)
        return str.slice(1, str.length - 1);
    return str;
}

// 坐标排序比较器
function compareByXCoordinate(coord1, coord2) {
    return coord2[0] - coord1[0];
}

// 全局过滤配置
var showControllersOnly = false;
var seriesFilter = "";
var filtersOnlySampleSeries = true;

// 修复时间戳偏移
function fixTimeStamps(series, offset){
    $.each(series, function(index, item) {
        $.each(item.data, function(index, coord) {
            coord[0] += offset;
        });
    });
}

// 判断 jQuery 对象是否为 Flot 图表
function isGraph(object){
    return object.data('plot') !== undefined;
}

// 初始化 Bootstrap 折叠面板事件
$(function() {
    $('.collapse').on('shown.bs.collapse', function(){
        collapse(this, false);
    }).on('hidden.bs.collapse', function(){
        collapse(this, true);
    });

    // 处理图标点击事件
    $(".glyphicon").on("mousedown", function(event){
        var tmp = $('.in:not(ul)');
        tmp.parent().parent().parent().find(".fa-chevron-up").removeClass("fa-chevron-down").addClass("fa-chevron-down");
        tmp.removeClass("in").addClass("out");
    });
});

/**
 * 将图表导出为 PNG 图片
 */
function exportToPNG(graphName, target) {
    var plot = $("#"+graphName).data('plot');
    if (!plot) return;

    var flotCanvas = plot.getCanvas();
    var image = flotCanvas.toDataURL().replace("image/png", "image/octet-stream");

    if ("download" in document.createElement("a")) {
        target.download = graphName + ".png";
        target.href = image;
    } else {
        document.location.href = image;
    }
}

// 生成概览图表的配置
function prepareOverviewOptions(graphOptions){
    var overviewOptions = {
        series: {
            shadowSize: 0,
            lines: { lineWidth: 1 },
            points: {
                show: getProperty('series.lines.show', graphOptions) == false,
                radius : 1
            }
        },
        xaxis: { ticks: 2, axisLabel: null },
        yaxis: { ticks: 2, axisLabel: null },
        legend: { show: false, container: null },
        grid: { hoverable: false },
        tooltip: false
    };
    return $.extend(true, {}, graphOptions, overviewOptions);
}

// 准备图表配置（处理时间轴偏移等）
function prepareOptions(options, data) {
    options.canvas = true;
    var extraOptions = data.extraOptions;
    if(extraOptions !== undefined){
        var xOffset = options.xaxis.mode === "time" ? 28800000 : 0;
        var yOffset = options.yaxis.mode === "time" ? 28800000 : 0;

        if(!isNaN(extraOptions.minX)) options.xaxis.min = parseFloat(extraOptions.minX) + xOffset;
        if(!isNaN(extraOptions.maxX)) options.xaxis.max = parseFloat(extraOptions.maxX) + xOffset;
        if(!isNaN(extraOptions.minY)) options.yaxis.min = parseFloat(extraOptions.minY) + yOffset;
        if(!isNaN(extraOptions.maxY)) options.yaxis.max = parseFloat(extraOptions.maxY) + yOffset;
    }
}

// 过滤、标记并排序图表数据系列
function prepareSeries(data, noMatchColor, ignoreFilterParam){
    var result = data.result;
    var ignoreFilter = ignoreFilterParam === true;

    if(!ignoreFilter && seriesFilter && (!filtersOnlySampleSeries || result.supportsControllersDiscrimination)){
        var regexp = new RegExp(seriesFilter, 'i');
        result.series = $.grep(result.series, function(series){
            return regexp.test(series.label);
        });
    }

    if(result.supportsControllersDiscrimination && showControllersOnly){
        result.series = $.grep(result.series, function(series){
            return series.isController;
        });
    }

    $.each(result.series, function(index, series) {
        series.data.sort(compareByXCoordinate);
        if(!(noMatchColor && noMatchColor === true)) {
            series.color = index;
        }
    });
}

// 设置图表缩放
function zoomPlot(plot, xmin, xmax, ymin, ymax){
    var axes = plot.getAxes();
    $.extend(true, axes, {
        xaxis: { options : { min: xmin, max: xmax } },
        yaxis: { options : { min: ymin, max: ymax } }
    });
    plot.setupGrid();
    plot.draw();
}

// 使图表支持缩放和概览联动
function setGraphZoomable(graphSelector, overviewSelector){
    var graph = $(graphSelector);
    var overview = $(overviewSelector);

    graph.on("mousedown", function() { return false; });
    overview.on("mousedown", function() { return false; });

    graph.on("plotselected", function (event, ranges) {
        if (ranges.xaxis.to - ranges.xaxis.from < 0.00001) ranges.xaxis.to = ranges.xaxis.from + 0.00001;
        if (ranges.yaxis.to - ranges.yaxis.from < 0.00001) ranges.yaxis.to = ranges.yaxis.from + 0.00001;

        var plot = graph.data('plot');
        zoomPlot(plot, ranges.xaxis.from, ranges.xaxis.to, ranges.yaxis.from, ranges.yaxis.to);
        plot.clearSelection();
        overview.data('plot').setSelection(ranges, true);
    });

    overview.on("plotselected", function (event, ranges) {
        graph.data('plot').setSelection(ranges);
    });

    overview.on("plotunselected", function () {
        var overviewAxes = overview.data('plot').getAxes();
        zoomPlot(graph.data('plot'), overviewAxes.xaxis.min, overviewAxes.xaxis.max, overviewAxes.yaxis.min, overviewAxes.yaxis.max);
    });
}

// 准备图表数据（仅提取选中的系列）
function prepareData(series, choiceContainer, customizeSeries){
    var datasets = [];
    choiceContainer.find("input:checked").each(function (index, item) {
        var key = $(item).attr("name");
        var i = 0;
        var size = series.length;
        while(i < size && series[i].label != key) i++;

        if(i < size){
            var currentSeries = series[i];
            datasets.push(currentSeries);
            if(customizeSeries) customizeSeries(currentSeries);
        }
    });
    return datasets;
}

// 忽略大小写的字符串排序
function sortAlphaCaseless(a,b){
    return a.toLowerCase() > b.toLowerCase() ? 1 : -1;
}

// 创建图表图例（Legend）
function createLegend(choiceContainer, infos) {
    var keys = [];
    $.each(infos.data.result.series, function(index, series){
        keys.push(series.label);
    });
    keys.sort(sortAlphaCaseless);

    $.each(keys, function(index, key) {
        var id = choiceContainer.attr('id') + index;
        $('<li />')
            .append($('<input id="' + id + '" name="' + key + '" type="checkbox" checked="checked" hidden />'))
            .append($('<label />', { 'text': key , 'for': id }))
            .appendTo(choiceContainer);
    });

    // 统一使用 jQuery 处理样式和事件
    choiceContainer.find("label")
        .on("click", function(){
            var $this = $(this);
            if ($this.css("color") !== "rgb(129, 129, 129)" ){
                $this.css("color", "#818181");
            } else {
                $this.css("color", "black");
            }
            $this.parent().children().children().toggleClass("legend-disabled");
        })
        .on("mousedown", function(event){ event.preventDefault(); })
        .on("mouseenter", function(){ $(this).css("cursor", "pointer"); });

    choiceContainer.find("input").on("click", function(){
        infos.createGraph();
    });
}

function uncheckAll(id){ toggleAll(id, false); }
function checkAll(id){ toggleAll(id, true); }