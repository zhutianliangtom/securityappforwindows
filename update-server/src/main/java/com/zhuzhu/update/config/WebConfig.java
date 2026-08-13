package com.zhuzhu.update.config;

import com.zhuzhu.update.security.AdminAuthInterceptor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.nio.file.Paths;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    private final AdminAuthInterceptor adminAuth;

    @Value("${upload.dir:./uploads}")
    private String uploadDir;

    public WebConfig(AdminAuthInterceptor adminAuth) {
        this.adminAuth = adminAuth;
    }

    /** 后台接口全部要求 Bearer token（登录接口内部放行） */
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(adminAuth)
                .addPathPatterns("/admin/api/**");
    }

    /** 上传的安装包与官网图片通过 /uploads/** 对外访问 */
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        String loc = Paths.get(uploadDir).toAbsolutePath().normalize().toUri().toString();
        if (!loc.endsWith("/")) {
            loc += "/";   // ResourceHttpRequestHandler 要求 location 以 / 结尾
        }
        registry.addResourceHandler("/uploads/**").addResourceLocations(loc);
    }

    /** /admin 直接访问时跳转到后台首页 */
    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addViewController("/admin").setViewName("forward:/admin/index.html");
    }
}
