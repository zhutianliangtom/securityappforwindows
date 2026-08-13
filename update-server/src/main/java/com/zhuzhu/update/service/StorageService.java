package com.zhuzhu.update.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.util.UUID;

/** 上传文件落盘：安装包存 uploads/pkg/，官网图片存 uploads/img/，均返回相对路径 */
@Service
public class StorageService {

    /** 上传根目录（绝对路径或相对工作目录），由环境变量 UPLOAD_DIR 覆盖 */
    @Value("${upload.dir:./uploads}")
    private String baseDir;

    /** 保存文件并计算 MD5，返回 {相对路径, MD5} */
    public Stored save(MultipartFile file, String sub) throws IOException {
        Path dir = Paths.get(baseDir).resolve(sub).toAbsolutePath().normalize();
        Files.createDirectories(dir);
        String name = sanitize(file.getOriginalFilename());
        String stored = UUID.randomUUID().toString().replace("-", "") + "_" + name;
        Path target = dir.resolve(stored);
        file.transferTo(target.toFile());
        String md5 = md5(target);
        return new Stored(sub + "/" + stored, md5);
    }

    /** 按相对路径解析为磁盘文件 */
    public Path resolve(String relPath) {
        return Paths.get(baseDir).resolve(relPath).toAbsolutePath().normalize();
    }

    private String sanitize(String name) {
        if (name == null || name.isBlank()) {
            return "file";
        }
        // 去除路径分隔符与非法字符，仅保留文件名
        String base = name.replace('\\', '/');
        base = base.substring(base.lastIndexOf('/') + 1);
        return base.replaceAll("[^\\w.\\-]", "_");
    }

    private String md5(Path p) throws IOException {
        MessageDigest md;
        try {
            md = MessageDigest.getInstance("MD5");
        } catch (Exception e) {
            throw new IOException("MD5 不可用", e);
        }
        try (InputStream in = Files.newInputStream(p)) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) {
                md.update(buf, 0, n);
            }
        }
        StringBuilder sb = new StringBuilder(32);
        for (byte b : md.digest()) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }

    public record Stored(String relPath, String md5) {
    }
}
