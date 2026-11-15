---
id: text/source_overview
category: text
title: 源文总览
description: 从项目源文提炼项目概述（故事梗概、题材、主题、世界观与源语言），供之后所有生成环节的提示词使用。
i18n:
  zh-TW:
    title: "原文總覽"
    description: "從專案原文整理出專案概述（故事大綱、題材、主題、世界觀與原文語言），供之後所有生成步驟的提示詞使用。"
  en:
    title: "Source overview"
    description: "Distills a project overview from the source text (synopsis, genre, themes, setting and source language) for the prompts of every later generation step."
  ru:
    title: "Обзор источника"
    description: "Составляет обзор проекта по исходному тексту (синопсис, жанр, темы, мир и язык источника) для промптов всех последующих этапов генерации."
  vi:
    title: "Tổng quan nguồn"
    description: "Rút ra tổng quan dự án từ văn bản nguồn (tóm tắt, thể loại, chủ đề, thế giới và ngôn ngữ nguồn) để dùng trong prompt của mọi bước tạo sau đó."
stage: source_overview
invoked_by:
  kind: user_action
  name: source_overview
applies_to:
  source_kind:
  - novel
  - screenplay
output_schema: lib.project.project_manager:ProjectOverview
slots:
  source_kind: 源文类型
  target_language: 输出语言，取项目源语言，缺省为中文
  source_content: 项目 source 目录下全部源文拼接的正文
protected: false
---
{{ variant("text/source_overview/task", source_kind) }}

**输出语言**：所有字符串值必须使用 {{ target_language }}；JSON 键名 / 枚举值保持英文。

{{ source_content }}
