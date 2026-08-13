package com.zhuzhu.update.web;

import com.zhuzhu.update.entity.AppVersion;
import com.zhuzhu.update.repo.AppVersionRepo;
import com.zhuzhu.update.repo.DownloadLogRepo;
import com.zhuzhu.update.security.AdminAuthService;
import com.zhuzhu.update.service.ContentService;
import com.zhuzhu.update.service.StatsService;
import com.zhuzhu.update.service.StorageService;
import com.zhuzhu.update.service.UpdateService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.time.format.DateTimeFormatter;
import java.util.*;

/** 管理后台接口（/admin/api/**，仅本机经 SSH 隧道访问，认证见 AdminAuthInterceptor） */
@RestController
@RequestMapping("/admin/api")
public class AdminController {

    private static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final AdminAuthService auth;
    private final ContentService contentService;
    private final StatsService statsService;
    private final UpdateService updateService;
    private final AppVersionRepo versionRepo;
    private final DownloadLogRepo logRepo;
    private final StorageService storage;

    public AdminController(AdminAuthService auth, ContentService contentService,
                           StatsService statsService, UpdateService updateService,
                           AppVersionRepo versionRepo, DownloadLogRepo logRepo,
                           StorageService storage) {
        this.auth = auth;
        this.contentService = contentService;
        this.statsService = statsService;
        this.updateService = updateService;
        this.versionRepo = versionRepo;
        this.logRepo = logRepo;
        this.storage = storage;
    }

    /** 登录：密码来自环境变量 ADMIN_PASSWORD，成功签发 24h Redis token */
    @PostMapping("/login")
    public ResponseEntity<Map<String, Object>> login(@RequestBody Map<String, String> body) {
        String token = auth.login(body.get("password"));
        if (token == null) {
            return ResponseEntity.status(401).body(Map.of("error", "密码错误"));
        }
        return ResponseEntity.ok(Map.of("token", token));
    }

    // ---------- 官网内容 ----------

    @GetMapping("/site")
    public Map<String, Object> getSite() {
        return Map.of("content", contentService.get());
    }

    @PutMapping("/site")
    public Map<String, Object> putSite(@RequestBody Map<String, Object> body) {
        Object c = body.get("content");
        @SuppressWarnings("unchecked")
        Map<String, Object> content = c instanceof Map<?, ?> m ? (Map<String, Object>) m : new LinkedHashMap<>();
        contentService.save(content);
        return Map.of("ok", true);
    }

    /** 官网图片上传：multipart 字段名 image，返回可访问 URL */
    @PostMapping("/site/image")
    public Map<String, Object> uploadImage(@RequestParam("image") MultipartFile image)
            throws IOException {
        if (image.isEmpty()) {
            return Map.of("error", "未选择文件");
        }
        StorageService.Stored s = storage.save(image, "img");
        return Map.of("url", "/uploads/" + s.relPath());
    }

    // ---------- 版本 / 安装包 ----------

    /** 发布新版本：multipart 字段 file/version/notes/force */
    @PostMapping("/version")
    public Map<String, Object> publish(@RequestParam("file") MultipartFile file,
                                       @RequestParam("version") String version,
                                       @RequestParam(value = "notes", defaultValue = "") String notes,
                                       @RequestParam(value = "force", defaultValue = "false") String force)
            throws IOException {
        if (file.isEmpty()) {
            return Map.of("error", "未选择安装包");
        }
        if (version == null || version.isBlank()) {
            return Map.of("error", "缺少版本号");
        }
        if (versionRepo.existsByVersion(version.trim())) {
            return Map.of("error", "版本号已存在：" + version.trim());
        }
        StorageService.Stored s = storage.save(file, "pkg");
        AppVersion v = new AppVersion();
        v.setVersion(version.trim());
        v.setFileName(file.getOriginalFilename() == null ? "installer" : file.getOriginalFilename());
        v.setFilePath(s.relPath());
        v.setFileSize(file.getSize());
        v.setMd5(s.md5());
        v.setNotes(notes);
        v.setForceUpdate("true".equalsIgnoreCase(force));
        versionRepo.save(v);
        return Map.of("ok", true);
    }

    /** 版本列表（按版本号降序，附每个版本的下载次数） */
    @GetMapping("/version")
    public List<Map<String, Object>> versions() {
        List<Map<String, Object>> out = new ArrayList<>();
        for (AppVersion v : updateService.allSorted()) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", v.getId());
            m.put("version", v.getVersion());
            m.put("fileName", v.getFileName());
            m.put("fileSize", v.getFileSize());
            m.put("notes", v.getNotes());
            m.put("forceUpdate", v.isForceUpdate());
            m.put("createdAt", v.getCreatedAt().format(FMT));
            m.put("downloads", logRepo.countByVersionId(v.getId()));
            out.add(m);
        }
        return out;
    }

    @DeleteMapping("/version/{id}")
    public Map<String, Object> deleteVersion(@PathVariable Long id) throws IOException {
        AppVersion v = versionRepo.findById(id).orElse(null);
        if (v == null) {
            return Map.of("error", "版本不存在");
        }
        try {
            Files.deleteIfExists(storage.resolve(v.getFilePath()));
        } catch (Exception ignored) {
        }
        versionRepo.delete(v);
        return Map.of("ok", true);
    }

    // ---------- 统计 ----------

    @GetMapping("/stats")
    public Map<String, Object> stats() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("totalDownloads", statsService.totalDownloads());
        out.put("versions", versions());
        out.put("trend", statsService.trend(30));
        return out;
    }
}
