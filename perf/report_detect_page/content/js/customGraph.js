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
 * 自定义图表交互逻辑模块
 * 负责处理 JMeter 报告中自定义图表的折叠、展开及图例全选功能
 */

$(document).ready(function() {

    // 1. 初始化可点击标题的交互样式
    // 建议在全局 CSS 中定义: .is-clickable { cursor: pointer; }
    $(".click-title")
        .addClass("is-clickable") // 通过添加类名控制样式，避免在 JS 中硬编码 CSS 属性
        .on("mousedown", function(event) {
            // 阻止默认的鼠标按下行为（如文本拖拽选中），提升点击体验
            event.preventDefault();
        });

    // 2. 重置面板头部的鼠标样式（覆盖可能继承的 pointer 样式）
    $(".portlet-header").css("cursor", "auto");
});

/**
 * 切换面板的折叠/展开状态图标 (FontAwesome)
 *
 * @param {HTMLElement|jQuery} elem - 触发折叠操作的面板头部 DOM 元素或 jQuery 对象
 * @param {boolean} collapsed - 面板当前是否处于折叠状态 (true: 折叠, false: 展开)
 */
function collapse(elem, collapsed) {
    // 统一转换为 jQuery 对象以便链式调用
    var $elem = $(elem);
    var $parent = $elem.parent();

    // 查找当前面板内的 FontAwesome 箭头图标
    var $icon = $parent.find(".fa-chevron-up, .fa-chevron-down");

    // 使用 toggleClass 简化逻辑：
    // 当 collapsed 为 true 时，添加 down 类，移除 up 类
    // 当 collapsed 为 false 时，添加 up 类，移除 down 类
    $icon.toggleClass("fa-chevron-down", collapsed)
         .toggleClass("fa-chevron-up", !collapsed);
}

/**
 * 批量切换图表图例的显示/隐藏状态（全选/取消全选）
 *
 * @param {string} containerId - 包含图例复选框的容器元素 ID
 * @param {boolean} isChecked - 目标选中状态 (true: 全选, false: 取消全选)
 */
function toggleAll(containerId, isChecked) {
    var $container = $("#" + containerId);
    if ($container.length === 0) {
        console.warn("ToggleAll: 未找到ID为 " + containerId + " 的容器");
        return;
    }

    // 获取容器内所有的复选框
    var $checkboxes = $container.find(':checkbox');

    // 更新复选框的 DOM 属性状态
    $checkboxes.prop('checked', isChecked);

    // 优化 DOM 遍历逻辑：
    // 原始代码使用 .parent().children().children() 极易因 HTML 结构变动而失效。
    // 现改为：从复选框向上查找最近的图例行容器(.legend-row)，再查找图例文本(.legend-label)。
    // 注：若实际 HTML 类名不同，请根据 JMeter 生成的实际 DOM 结构微调此处的选择器。
    $checkboxes.closest('.legend-row').find('.legend-label').toggleClass("legend-disabled", !isChecked);
}