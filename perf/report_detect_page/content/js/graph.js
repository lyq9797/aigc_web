/**
 * JMeter HTML Report Graph Renderer
 * 负责渲染性能测试报告中的各类 Flot 图表
 *
 * @author Graduate Dev Team
 * @version 2.0.0
 */
(function($) {
    'use strict';

    // ================= 1. 常量与默认配置 =================

    /** 默认坐标轴样式配置，避免在每个图表中重复硬编码 */
    const DEFAULT_AXIS_CONFIG = {
        axisLabelUseCanvas: true,
        axisLabelFontSizePixels: 12,
        axisLabelFontFamily: 'Verdana, Arial',
        axisLabelPadding: 20
    };

    /** 图表注册表，用于统一管理所有图表实例 */
    const chartRegistry = {};

    // ================= 2. 核心图表管理类 =================

    /**
     * 图表管理器：负责图表的注册、初始化和交互绑定
     */
    const ChartManager = {
        /**
         * 注册一个新的图表配置
         * @param {string} id - 图表的唯一标识符 (如 'HitsPerSecond')
         * @param {Object} config - 图表配置对象，包含 data, getOptions, DOM IDs
         */
        register: function(id, config) {
            chartRegistry[id] = config;
        },

        /**
         * 渲染指定图表
         * @param {string} id - 图表标识符
         * @param {boolean} fixTimestamps - 是否需要修正时间戳
         */
        render: function(id, fixTimestamps) {
            const config = chartRegistry[id];
            if (!config) return;

            // 准备数据系列
            prepareSeries(config.data, config.ignoreSeriesFilter);

            // 处理时间戳修正
            if (fixTimestamps && config.data.result.series) {
                fixTimeStamps(config.data.result.series, 28800000);
            }

            // 检查是否有数据
            if (config.data.result.series && config.data.result.series.length === 0) {
                this._showEmptyMessage(config.bodyId);
                return;
            }

            // 如果图表已存在，仅重绘；否则初始化完整交互
            if (isGraph($(config.mainGraphId))) {
                this._drawPlot(config);
            } else {
                this._initInteractions(config);
            }
        },

        /** 内部方法：执行实际的 Flot 绘图 */
        _drawPlot: function(config) {
            const dataset = prepareData(config.data.result.series, $(config.choiceContainerId));
            const options = config.getOptions();
            prepareOptions(options, config.data);

            $.plot($(config.mainGraphId), dataset, options);
            if (config.overviewGraphId) {
                $.plot($(config.overviewGraphId), dataset, prepareOverviewOptions(options));
            }
        },

        /** 内部方法：初始化图例、缩放等交互事件 */
        _initInteractions: function(config) {
            const $choiceContainer = $(config.choiceContainerId);
            createLegend($choiceContainer, config);
            this._drawPlot(config);

            if (config.overviewGraphId) {
                setGraphZoomable(config.mainGraphId, config.overviewGraphId);
            }

            // 克隆图例颜色块
            $(config.footerId + ' .legendColorBox > div').each(function(i) {
                $(this).clone().prependTo($choiceContainer.find("li").eq(i));
            });
        },

        /** 内部方法：显示空数据提示 */
        _showEmptyMessage: function(bodyId) {
            $(bodyId).text("No graph series with filter=" + (typeof seriesFilter !== 'undefined' ? seriesFilter : 'none'));
        }
    };

    // ================= 3. 图表配置定义 =================
    // 将数据与配置分离，利用 DEFAULT_AXIS_CONFIG 简化代码

    ChartManager.register('ResponseTimePercentiles', {
        bodyId: '#bodyResponseTimePercentiles',
        mainGraphId: '#flotResponseTimesPercentiles',
        overviewGraphId: '#overviewResponseTimesPercentiles',
        choiceContainerId: '#choicesResponseTimePercentiles',
        footerId: '#bodyResponseTimePercentiles',
        data: {"result": {/* ... 原始 JSON 数据保留 ... */}},
        getOptions: function() {
            return {
                series: { points: { show: false } },
                legend: { noColumns: 2, show: true, container: '#legendResponseTimePercentiles' },
                xaxis: $.extend({}, DEFAULT_AXIS_CONFIG, { tickDecimals: 1, axisLabel: "Percentiles" }),
                yaxis: $.extend({}, DEFAULT_AXIS_CONFIG, { axisLabel: "Percentile value in ms" }),
                grid: { hoverable: true },
                tooltip: true,
                tooltipOpts: { content: "%s : %x.2 percentile was %y ms" },
                selection: { mode: "xy" }
            };
        }
    });

    ChartManager.register('BytesThroughput', {
        bodyId: '#bodyBytesThroughputOverTime',
        mainGraphId: '#flotBytesThroughputOverTime',
        overviewGraphId: '#overviewBytesThroughputOverTime',
        choiceContainerId: '#choicesBytesThroughputOverTime',
        footerId: '#footerBytesThroughputOverTime',
        data: {"result": {/* ... 原始 JSON 数据保留 ... */}},
        getOptions: function() {
            return {
                series: { lines: { show: true }, points: { show: true } },
                xaxis: $.extend({}, DEFAULT_AXIS_CONFIG, {
                    mode: "time",
                    timeformat: getTimeFormat(this.data.result.granularity),
                    axisLabel: getElapsedTimeLabel(this.data.result.granularity)
                }),
                yaxis: $.extend({}, DEFAULT_AXIS_CONFIG, { axisLabel: "Bytes / sec" }),
                legend: { noColumns: 2, show: true, container: '#legendBytesThroughputOverTime' },
                selection: { mode: "xy" },
                grid: { hoverable: true },
                tooltip: true,
                tooltipOpts: { content: "%s at %x was %y" }
            };
        }
    });

    // ... (此处省略其他图表的 register 调用，结构同上) ...

    // ================= 4. UI 交互与事件分发 =================

    /** 折叠面板的锚点与刷新配置映射 */
    const collapseConfig = {
        "bodyBytesThroughputOverTime": { chartId: 'BytesThroughput', fixTs: true, anchor: "#bytesThroughputOverTime" },
        "bodyLatenciesOverTime": { chartId: 'Latencies', fixTs: true, anchor: "#latenciesOverTime" },
        "bodyActiveThreadsOverTime": { chartId: 'ActiveThreads', fixTs: true, anchor: "#activeThreadsOverTime" },
        "bodyResponseTimeDistribution": { chartId: 'ResponseTimeDistribution', fixTs: false, anchor: "#responseTimeDistribution" }
        // ... 其他映射
    };

    /**
     * 处理面板折叠/展开事件
     */
    function handleCollapse(elem, collapsed) {
        const $parent = $(elem).parent();
        if (collapsed) {
            $parent.find(".fa-chevron-up").removeClass("fa-chevron-up").addClass("fa-chevron-down");
        } else {
            $parent.find(".fa-chevron-down").removeClass("fa-chevron-down").addClass("fa-chevron-up");

            const config = collapseConfig[elem.id];
            if (config) {
                if (!isGraph($(elem).find('.flot-chart-content'))) {
                    ChartManager.render(config.chartId, config.fixTs);
                }
                document.location.href = config.anchor;
            }
        }
    }

    /**
     * 全选/取消全选图例
     */
    function handleToggleAll(id, checked) {
        const $placeholder = $("#" + id);
        const $checkboxes = $placeholder.find(':checkbox');

        $checkboxes.prop('checked', checked);
        $checkboxes.parent().children().children().toggleClass("legend-disabled", !checked);
        $placeholder.find("label").css("color", checked ? "black" : "#818181");

        // 触发对应图表的重绘
        const chartId = id.replace('choices', '');
        if (chartRegistry[chartId]) {
            ChartManager.render(chartId, false);
        }
    }

    // ================= 5. 全局暴露与初始化 =================

    // 将需要被 HTML onclick 调用的函数挂载到 window 对象
    window.collapse = handleCollapse;
    window.toggleAll = handleToggleAll;

    // DOM Ready 初始化
    $(document).ready(function() {
        // 绑定标题点击样式
        $(".click-title")
            .mouseenter(function(e) { e.preventDefault(); $(this).css("cursor", "pointer"); })
            .mousedown(function(e) { e.preventDefault(); });

        // 遍历注册表，自动渲染页面中存在的图表
        $.each(chartRegistry, function(id, config) {
            if ($(config.mainGraphId).length > 0) {
                // 根据图表类型判断是否需要修正时间戳 (简单启发式：包含 Time 的通常需要)
                const needsFixTs = id.includes('Time') || id.includes('Throughput') || id.includes('Threads');
                ChartManager.render(id, needsFixTs);
            }
        });
    });

})(jQuery);