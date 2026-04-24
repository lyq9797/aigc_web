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

// 页面加载完成后初始化交互事件
$(document).ready(function() {
    // 为可点击的标题添加鼠标悬停效果
    $(".click-title").mouseenter(function(e) {
        e.preventDefault();
        $(this).css("cursor", "pointer");
    });

    // 阻止标题的默认mousedown行为（防止文本选中等干扰）
    $(".click-title").mousedown(function(event) {
        event.preventDefault();
    });

    // 重置面板头部的鼠标样式
    $(".portlet-header").css("cursor", "auto");
});

/**
 * 切换面板的折叠/展开图标
 * @param {HTMLElement} elem - 触发折叠的面板头部元素
 * @param {boolean} collapsed - 当前是否处于折叠状态
 */
function collapse(elem, collapsed) {
    if (collapsed) {
        // 如果是折叠状态，将向上箭头改为向下箭头
        $(elem).parent().find(".fa-chevron-up")
            .removeClass("fa-chevron-up")
            .addClass("fa-chevron-down");
    } else {
        // 如果是展开状态，将向下箭头改为向上箭头
        $(elem).parent().find(".fa-chevron-down")
            .removeClass("fa-chevron-down")
            .addClass("fa-chevron-up");
    }
}

/**
 * 全选/取消全选图表的图例复选框
 * @param {string} id - 包含复选框的容器元素ID
 * @param {boolean} checked - 是否选中
 */
function toggleAll(id, checked) {
    var placeholder = document.getElementById(id);
    var cases = $(placeholder).find(':checkbox');

    // 更新复选框的选中状态
    cases.prop('checked', checked);

    // 切换图例的禁用样式（通过多层级查找定位到图例文本元素）
    $(cases).parent().children().children().toggleClass("legend-disabled", !checked);
}