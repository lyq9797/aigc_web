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
 * JMeter Dashboard 公共工具库 (dashboard-commons.js)
 * 提供时间格式化、图表数据处理、DOM 交互等公共方法
 * =====================================================================
 */

// 初始化全局命名空间，避免全局变量污染
window.JMeterReport = window.JMeterReport || {};

(function(JR) {
    'use strict';

    // ==================== 1. 常量与 Polyfill ====================

    /** 时间常量（毫秒） */
    JR.TIME = {
        DAY: 86400000,
        HOUR: 3600000,
        MINUTE: 60000
    };

    /**
     * 修复 JavaScript 原生 Math 方法处理浮点数精度丢失的问题
     * 挂载到全局 Math 对象以便其他地方调用 (如 Math.round10)
     */
    (function initMathPolyfills() {
        const decimalAdjust = (type, value, exp) => {
            if (typeof exp === 'undefined' || +exp === 0) return Math[type](value);
            value = +value;
            exp = +exp;
            if (isNaN(value) || !(typeof exp === 'number' && exp % 1 === 0)) return NaN;

            value = value.toString().split('e');
            value = Math[type](+(value[0] + 'e' + (value[1] ? (+value[1] - exp) : -exp)));
            value = value.toString().split('e');
            return +(value[0] + 'e' + (value[1] ? (+value[1] + exp) : exp));
        };

        if (!Math.round10) Math.round10 = (v, e) => decimalAdjust('round', v, e);
        if (!Math.floor10) Math.floor10 = (v, e) => decimalAdjust('floor', v, e);
        if (!Math.ceil10)  Math.ceil10  = (v, e) => decimalAdjust('ceil', v, e);
    })();

    // ==================== 2. 全局配置状态 ====================
    // 将原本散落的全局变量收拢到 Config 对象中

    JR.Config = {
        showControllersOnly: false,
        seriesFilter: "",
        filtersOnlySampleSeries: true
    };

    // ==================== 3. 工具函数 (Utils) ====================

    /**
     * 将毫秒数格式化为可读的时间字符串
     * @param {number|string} duration - 毫秒数
     * @param {boolean} [spaced=false] - 数值与单位间是否加空格
     * @returns {string} 格式化后的字符串，如 "1 day(s) 2 hour(s)"
     */
    JR.formatDuration = function(duration, spaced) {
        if (typeof duration === "string") return duration;

        const formatUnit = (val, unit) => spaced ? `${val} ${unit}` : `${val}${unit}`;

        let days = Math.floor(duration / JR.TIME.DAY);
        duration %= JR.TIME.DAY;

        let hours = Math.floor(duration / JR.TIME.HOUR);
        duration %= JR.TIME.HOUR;

        let minutes = Math.floor(duration / JR.TIME.MINUTE);
        duration %= JR.TIME.MINUTE;

        let seconds = Math.floor(duration / 1000);
        duration %= 1000;

        const parts = [];
        if (days > 0) parts.push(formatUnit(days, "day(s)"));
        if (hours > 0) parts.push(formatUnit(hours, "hour(s)"));
        if (minutes > 0) parts.push(formatUnit(minutes, "min"));
        if (seconds > 0) parts.push(formatUnit(seconds, "sec"));
        if (duration > 0) parts.push(formatUnit(duration, "ms"));

        return parts.join(" ");
    };

    /** 安全获取对象深层属性 (如 'a.b.c') */
    JR.getProperty = function(key, obj) {
        return key.split('.').reduce((prop, subprop) => prop && prop[subprop], obj);
    };

    /** 移除字符串首尾引号 */
    JR.unquote = function(str, quoteChar = '"') {
        if (str.length > 0 && str[0] === quoteChar && str[str.length - 1] === quoteChar) {
            return str.slice(1, -1);
        }
        return str;
    };

    // ==================== 4. 图表数据处理 (Chart Data) ====================

    /** 坐标排序比较器 (按 X 轴降序) */
    JR.compareByXCoordinate = (coord1, coord2) => coord2[0] - coord1[0];

    /** 修复时间戳偏移 */
    JR.fixTimeStamps = function(series, offset) {
        $.each(series, (_, item) => {
            $.each(item.data, (_, coord) => { coord[0] += offset; });
        });
    };

    /**
     * 过滤、标记并排序图表数据系列
     * @param {Object} data - 包含 result.series 的数据对象
     * @param {boolean} noMatchColor - 是否禁用颜色自动匹配
     * @param {boolean} ignoreFilter - 是否忽略全局过滤器
     */
    JR.prepareSeries = function(data, noMatchColor, ignoreFilter) {
        const result = data.result;
        const cfg = JR.Config;

        // 1. 应用文本过滤
        if (!ignoreFilter && cfg.seriesFilter && (!cfg.filtersOnlySampleSeries || result.supportsControllersDiscrimination)) {
            const regexp = new RegExp(cfg.seriesFilter, 'i');
            result.series = $.grep(result.series, series => regexp.test(series.label));
        }

        // 2. 应用控制器过滤
        if (result.supportsControllersDiscrimination && cfg.showControllersOnly) {
            result.series = $.grep(result.series, series => series.isController);
        }

        // 3. 排序并分配颜色
        $.each(result.series, (index, series) => {
            series.data.sort(JR.compareByXCoordinate);
            if (!noMatchColor) series.color = index;
        });
    };

    /** 准备图表配置（处理时间轴偏移等） */
    JR.prepareOptions = function(options, data) {
        options.canvas = true;
        const extra = data.extraOptions;
        if (!extra) return;

        const xOffset = options.xaxis.mode === "time" ? 28800000 : 0;
        const yOffset = options.yaxis.mode === "time" ? 28800000 : 0;

        if (!isNaN(extra.minX)) options.xaxis.min = parseFloat(extra.minX) + xOffset;
        if (!isNaN(extra.maxX)) options.xaxis.max = parseFloat(extra.maxX) + xOffset;
        if (!isNaN(extra.minY)) options.yaxis.min = parseFloat(extra.minY) + yOffset;
        if (!isNaN(extra.maxY)) options.yaxis.max = parseFloat(extra.maxY) + yOffset;
    };

    // ==================== 5. 图表交互与渲染 (Chart UI) ====================

    /** 设置图表缩放和概览联动 */
    JR.setGraphZoomable = function(graphSelector, overviewSelector) {
        const $graph = $(graphSelector);
        const $overview = $(overviewSelector);

        // 阻止默认的拖拽选中行为
        $graph.on("mousedown", () => false);
        $overview.on("mousedown", () => false);

        // 主图框选缩放
        $graph.on("plotselected", (event, ranges) => {
            if (ranges.xaxis.to - ranges.xaxis.from < 0.00001) ranges.xaxis.to = ranges.xaxis.from + 0.00001;
            if (ranges.yaxis.to - ranges.yaxis.from < 0.00001) ranges.yaxis.to = ranges.yaxis.from + 0.00001;

            const plot = $graph.data('plot');
            const axes = plot.getAxes();
            $.extend(true, axes, {
                xaxis: { options: { min: ranges.xaxis.from, max: ranges.xaxis.to } },
                yaxis: { options: { min: ranges.yaxis.from, max: ranges.yaxis.to } }
            });
            plot.setupGrid();
            plot.draw();
            plot.clearSelection();

            $overview.data('plot').setSelection(ranges, true);
        });

        // 概览图联动
        $overview.on("plotselected", (event, ranges) => $graph.data('plot').setSelection(ranges));
        $overview.on("plotunselected", () => {
            const oAxes = $overview.data('plot').getAxes();
            const plot = $graph.data('plot');
            const axes = plot.getAxes();
            $.extend(true, axes, {
                xaxis: { options: { min: oAxes.xaxis.min, max: oAxes.xaxis.max } },
                yaxis: { options: { min: oAxes.yaxis.min, max: oAxes.yaxis.max } }
            });
            plot.setupGrid();
            plot.draw();
        });
    };

    /**
     * 创建图表图例（Legend）并绑定交互事件
     * 优化：使用事件委托替代循环绑定，减少内存占用
     */
    JR.createLegend = function($choiceContainer, infos) {
        const keys = infos.data.result.series.map(s => s.label).sort((a, b) => a.toLowerCase() > b.toLowerCase() ? 1 : -1);

        // 1. 渲染 DOM
        const $ul = $('<ul></ul>');
        $.each(keys, (index, key) => {
            const id = $choiceContainer.attr('id') + index;
            const $li = $('<li></li>');
            $li.append(`<input id="${id}" name="${key}" type="checkbox" checked hidden />`);
            $li.append(`<label for="${id}">${key}</label>`);
            $ul.append($li);
        });
        $choiceContainer.append($ul);

        // 2. 事件委托处理交互
        $choiceContainer
            .on("click", "label", function() {
                const $label = $(this);
                const isDisabled = $label.css("color") === "rgb(129, 129, 129)";
                $label.css("color", isDisabled ? "black" : "#818181");
                $label.siblings('input').prop('checked', isDisabled);
                $label.parent().find('.legend-color-box, .legend-label').toggleClass("legend-disabled", !isDisabled);
            })
            .on("mousedown", "label", e => e.preventDefault())
            .on("mouseenter", "label", function() { $(this).css("cursor", "pointer"); })
            .on("change", "input", () => infos.createGraph()); // 监听 checkbox 状态变化
    };

    /** 导出图表为 PNG */
    JR.exportToPNG = function(graphName, target) {
        const plot = $("#" + graphName).data('plot');
        if (!plot) return;

        const image = plot.getCanvas().toDataURL().replace("image/png", "image/octet-stream");
        if ("download" in document.createElement("a")) {
            target.download = graphName + ".png";
            target.href = image;
        } else {
            document.location.href = image;
        }
    };

})(window.JMeterReport);

// ==================== 6. 全局兼容与初始化 ====================

// 为了兼容 JMeter 原生的 dashboard.js 调用，将常用方法映射回全局作用域
const JR = window.JMeterReport;
window.formatDuration = JR.formatDuration;
window.getProperty = JR.getProperty;
window.unquote = JR.unquote;
window.fixTimeStamps = JR.fixTimeStamps;
window.prepareSeries = JR.prepareSeries;
window.prepareOptions = JR.prepareOptions;
window.setGraphZoomable = JR.setGraphZoomable;
window.createLegend = JR.createLegend;
window.exportToPNG = JR.exportToPNG;

// 暴露全局配置变量以兼容旧代码
window.showControllersOnly = JR.Config.showControllersOnly;
window.seriesFilter = JR.Config.seriesFilter;
window.filtersOnlySampleSeries = JR.Config.filtersOnlySampleSeries;

// 初始化 Bootstrap 折叠面板事件
$(function() {
    $('.collapse').on('shown.bs.collapse', function(){ collapse(this, false); })
                  .on('hidden.bs.collapse', function(){ collapse(this, true); });
});