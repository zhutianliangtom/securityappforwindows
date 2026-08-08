package com.example.sparkchaindemo.ai.feature;

import android.os.Bundle;
import android.text.TextUtils;
import android.util.Log;
import android.view.View;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import com.example.sparkchaindemo.R;
import com.iflytek.sparkchain.core.feature.Feature;
import com.iflytek.sparkchain.core.feature.FeatureCallbacks;

import java.io.File;
import java.io.FileInputStream;

public class FeatureActivity extends AppCompatActivity {
    private static final String TAG = "FeatureActivity";
    TextView chatOutputText;
    boolean isrun = false;
    Feature mFeature;
    String featureId = "20260306183915929OiiWt8fSbDaHeRSk";

    String rltKey;

    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.ai_feature);
        chatOutputText = findViewById(R.id.output_text);
        init();
    }

    protected void init() {
        findViewById(R.id.reg_feature).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                regFeature();
            }
        });
        findViewById(R.id.update_feature).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                updateFeature();
            }
        });
        findViewById(R.id.dele_feature).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                deleFeature();
            }
        });
    }

    private void deleFeature() {
        if (TextUtils.isEmpty(featureId)) {
            Toast.makeText(this, "声纹id为空", Toast.LENGTH_SHORT).show();
            return;
        }
        if (isrun) return;
        isrun = true;
        if (mFeature == null) {
            mFeature = new Feature();
        }
        mFeature.registerCallbacks(mFeatureCallbacks);
        int ret = mFeature.featureDelete(featureId, "delete");
        Log.d(TAG, "deleFeature ret:" + ret);
    }

    private void updateFeature() {
        byte[] data = null;
        try {
            File file = new File("/sdcard/iflytek/asr/cn.pcm");
            FileInputStream fis = new FileInputStream(file);
            data = new byte[(int) file.length()];
            fis.read(data);
            fis.close();
        } catch (Exception e) {
        }
        if (data == null) {
            Toast.makeText(this, "请放入声纹文件到/sdcard/iflytek/asr/cn.pcm", Toast.LENGTH_SHORT).show();
            return;
        }
        if (TextUtils.isEmpty(featureId)) {
            Toast.makeText(this, "声纹id为空", Toast.LENGTH_SHORT).show();
            return;
        }
        if (isrun) return;
        isrun = true;
        if (mFeature == null) {
            mFeature = new Feature();
        }
        mFeature.registerCallbacks(mFeatureCallbacks);
        int ret = mFeature.featureUpdate(data, "raw", featureId, "update");
        Log.d(TAG, "updateFeature ret:" + ret);
    }

    private void regFeature() {
        byte[] data = null;
        try {
            File file = new File("/sdcard/iflytek/asr/cn.pcm");
            FileInputStream fis = new FileInputStream(file);
            data = new byte[(int) file.length()];
            fis.read(data);
            fis.close();
        } catch (Exception e) {
        }
        if (data == null) {
            Toast.makeText(this, "请放入声纹文件到/sdcard/iflytek/asr/cn.pcm", Toast.LENGTH_SHORT).show();
            return;
        }
        if (isrun) return;
        isrun = true;
        if (mFeature == null) {
            mFeature = new Feature();
        }
        mFeature.registerCallbacks(mFeatureCallbacks);
        int ret = mFeature.featureRegister(data, "raw", "userid-123456", "register");
        Log.d(TAG, "regFeature ret:" + ret);
    }

    FeatureCallbacks mFeatureCallbacks = new FeatureCallbacks() {
        @Override
        public void onResult(Feature.FeatureResult result, Object usrTag) {
            Log.d(TAG, "key :" + result.getFeatureId() + " tag:" + usrTag);
            isrun = false;
            if(usrTag == "register")
            {
                featureId = result.getFeatureId();
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        chatOutputText.append("register success! featureId :" + result.getFeatureId() + "\n");
                    }
                });
            } else if(usrTag == "update")
            {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        chatOutputText.append("update success!featureId :" + featureId + "\n");
                    }
                });
            } else if (usrTag == "delete") {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        chatOutputText.append("delete success!\n");
                    }
                });
            }

        }

        @Override
        public void onError(Feature.FeatureError error, Object usrTag) {
            Log.d(TAG, "FeatureError error:" + error.getCode() + " msg:" + error.getMessage() + " tag:" + usrTag);
            isrun = false;
        }
    };
}
