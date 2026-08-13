package com.zhuzhu.update.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.zhuzhu.update.entity.SiteContent;
import com.zhuzhu.update.repo.SiteContentRepo;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.Map;

/** 官网内容：单行 JSON 存储，默认内置一套初始内容 */
@Service
public class ContentService {

    private static final String KEY = "site";

    private final SiteContentRepo repo;
    private final ObjectMapper mapper;

    public ContentService(SiteContentRepo repo, ObjectMapper mapper) {
        this.repo = repo;
        this.mapper = mapper;
    }

    /** 官网内容（Map），无记录时写入默认内容并返回 */
    public Map<String, Object> get() {
        SiteContent row = repo.findByCkey(KEY).orElseGet(this::initDefault);
        try {
            return mapper.readValue(row.getContentJson(), new TypeReference<>() {
            });
        } catch (Exception e) {
            return new LinkedHashMap<>();
        }
    }

    /** 保存官网内容（contentJson 由调用方传入的 Map 序列化） */
    public void save(Map<String, Object> content) {
        try {
            String json = mapper.writeValueAsString(content);
            SiteContent row = repo.findByCkey(KEY).orElseGet(SiteContent::new);
            row.setCkey(KEY);
            row.setContentJson(json);
            row.setUpdatedAt(LocalDateTime.now());
            repo.save(row);
        } catch (Exception e) {
            throw new IllegalStateException("内容序列化失败", e);
        }
    }

    private SiteContent initDefault() {
        Map<String, Object> content = new LinkedHashMap<>();
        content.put("title", "WinAppMigrator");
        content.put("slogan", "把电脑交给 AI，替你把活干完");
        content.put("description", "Windows 应用迁移与系统优化工具，内置 AI Copilot：观察屏幕、理解指令、自动完成电脑操作。");
        content.put("heroImage", "");
        Map<String, Object> f1 = new LinkedHashMap<>();
        f1.put("title", "应用迁移");
        f1.put("desc", "一键迁移应用安装目录，保留设置与数据，杜绝 C 盘膨胀。");
        Map<String, Object> f2 = new LinkedHashMap<>();
        f2.put("title", "AI 助手");
        f2.put("desc", "直接输入任务，AI 自动截屏分析、点击输入，像真人一样操作电脑。");
        Map<String, Object> f3 = new LinkedHashMap<>();
        f3.put("title", "系统优化");
        f3.put("desc", "内存优化、启动项治理、安全防护，让老电脑重新流畅。");
        content.put("features", java.util.List.of(f1, f2, f3));
        Map<String, Object> s1 = new LinkedHashMap<>();
        s1.put("label", "迁移应用");
        s1.put("value", "50+");
        Map<String, Object> s2 = new LinkedHashMap<>();
        s2.put("label", "AI 技能");
        s2.put("value", "20+");
        content.put("stats", java.util.List.of(s1, s2));
        try {
            SiteContent row = new SiteContent();
            row.setCkey(KEY);
            row.setContentJson(mapper.writeValueAsString(content));
            row.setUpdatedAt(LocalDateTime.now());
            return repo.save(row);
        } catch (Exception e) {
            throw new IllegalStateException("初始化官网内容失败", e);
        }
    }
}
