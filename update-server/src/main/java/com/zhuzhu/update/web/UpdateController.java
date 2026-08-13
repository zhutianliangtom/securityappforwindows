package com.zhuzhu.update.web;

import com.zhuzhu.update.entity.AppVersion;
import com.zhuzhu.update.entity.DownloadLog;
import com.zhuzhu.update.repo.AppVersionRepo;
import com.zhuzhu.update.repo.DownloadLogRepo;
import com.zhuzhu.update.service.StatsService;
import com.zhuzhu.update.service.StorageService;
import com.zhuzhu.update.service.UpdateService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;

/** 客户端更新检查与安装包下载 */
@RestController
@RequestMapping("/api/update")
public class UpdateController {

    private final UpdateService updateService;
    private final AppVersionRepo versionRepo;
    private final DownloadLogRepo logRepo;
    private final StatsService statsService;
    private final StorageService storage;

    public UpdateController(UpdateService updateService, AppVersionRepo versionRepo,
                            DownloadLogRepo logRepo, StatsService statsService,
                            StorageService storage) {
        this.updateService = updateService;
        this.versionRepo = versionRepo;
        this.logRepo = logRepo;
        this.statsService = statsService;
        this.storage = storage;
    }

    /** 客户端每 30s 轮询：version=客户端当前版本号，platform=windows/macos 等 */
    @GetMapping("/check")
    public Map<String, Object> check(@RequestParam String version,
                                     @RequestParam(defaultValue = "windows") String platform) {
        AppVersion latest = updateService.latest();
        Map<String, Object> out = new LinkedHashMap<>();
        if (latest == null) {
            out.put("hasUpdate", false);
            return out;
        }
        boolean hasUpdate = UpdateService.compare(latest.getVersion(), version) > 0;
        out.put("hasUpdate", hasUpdate);
        out.put("latest", latest.getVersion());
        out.put("notes", latest.getNotes());
        out.put("size", latest.getFileSize());
        out.put("md5", latest.getMd5());
        out.put("force", latest.isForceUpdate());
        out.put("url", "/api/update/download/" + latest.getId());
        return out;
    }

    /** 安装包下载：返回文件流并记录一条下载日志 */
    @GetMapping("/download/{id}")
    public ResponseEntity<FileSystemResource> download(@PathVariable Long id,
                                                       HttpServletRequest request) {
        AppVersion v = versionRepo.findById(id).orElse(null);
        if (v == null) {
            return ResponseEntity.notFound().build();
        }
        Path file = storage.resolve(v.getFilePath());
        if (!Files.isRegularFile(file)) {
            return ResponseEntity.notFound().build();
        }
        recordDownload(v, request);
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + v.getFileName() + "\"")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .contentLength(v.getFileSize())
                .body(new FileSystemResource(file));
    }

    private void recordDownload(AppVersion v, HttpServletRequest request) {
        try {
            DownloadLog log = new DownloadLog();
            log.setVersionId(v.getId());
            log.setIp(clientIp(request));
            String ua = request.getHeader("User-Agent");
            log.setUserAgent(ua != null && ua.length() > 255 ? ua.substring(0, 255) : ua);
            logRepo.save(log);
            statsService.invalidateTotal();
        } catch (Exception ignored) {
            // 统计失败不影响下载
        }
    }

    /** nginx 反代时取 X-Real-IP，否则取 remoteAddr */
    private String clientIp(HttpServletRequest request) {
        String real = request.getHeader("X-Real-IP");
        return real != null && !real.isBlank() ? real : request.getRemoteAddr();
    }
}
