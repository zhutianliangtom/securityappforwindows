package com.example.sparkchaindemo.ai.ist;

import android.os.Bundle;
import android.text.TextUtils;
import android.util.Log;
import android.view.View;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;

import com.example.sparkchaindemo.R;
import com.iflytek.sparkchain.core.SparkChain;
import com.iflytek.sparkchain.core.SparkChainConfig;
import com.iflytek.sparkchain.core.ist.IST;
import com.iflytek.sparkchain.core.ist.ISTCallbacks;

import java.io.FileOutputStream;

public class ISTActivity extends AppCompatActivity {
    private static final String TAG = "AEELog";

    private final String appID = "";
    private final String apiKey = "";
    private final String apiSecret = "";

    TextView chatOutputText;

    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.api_ist);
        chatOutputText = findViewById(R.id.chat_output_text);
        init();
    }

    protected void init() {
        listener();
    }

    private void listener(){
        findViewById(R.id.start_init).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                //初始化
                initSDK();
            }
        });
        findViewById(R.id.test_btn).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                chatOutputText.setText("");
                new Thread(new Runnable() {
                    @Override
                    public void run() {
                        testIst(false);
                    }
                }).start();
            }
        });
        findViewById(R.id.test_btn_bm).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                chatOutputText.setText("");
                new Thread(new Runnable() {
                    @Override
                    public void run() {
                        testIst(true);
                    }
                }).start();
            }
        });

        findViewById(R.id.test_btn_stop).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                mIST.stop();
                isrun = false;
            }
        });
        findViewById(R.id.creat_task_btn).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                chatOutputText.setText("");
                if(!TextUtils.isEmpty(url)){
                    new Thread(new Runnable() {
                        @Override
                        public void run() {
                            if(isrun)return;
                            mIST.createTask("createTask",url,"audio/L16;rate=16000", "raw","tag");
                        }
                    }).start();
                }
            }
        });
        findViewById(R.id.get_result_btn).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                chatOutputText.setText("");
                if(!TextUtils.isEmpty(taskID)){
                    new Thread(new Runnable() {
                        @Override
                        public void run() {
                            if(isrun)return;
                            mIST.queryTask(taskID,"tag");
                        }
                    }).start();
                }
            }
        });

    }

    private void initSDK(){
        SparkChainConfig config = SparkChainConfig.builder()
                .appID(appID)
                .apiKey(apiKey)
                .apiSecret(apiSecret)
                .logLevel(666);
        int ret = SparkChain.getInst().init(getApplicationContext(), config);
        Log.d(TAG,"sparkChain int ret:" + ret);
        chatOutputText.setText("sparkChain int ret:" + ret);
    }

    private IST mIST;
    private String orderid = "";
    boolean isrun = false;
    String language = "zh_cn";
    String domain = "pro_ost_ed";
    String accent = "mandarin";
    String url = "";
    String taskID = "";
    private void testIst(boolean ismp) {
        if(isrun)return;
        isrun = true;
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                chatOutputText.setText("");
            }
        });
        if(mIST == null)mIST = new IST();

        mIST.language(language);
        mIST.domain(domain);
        mIST.accent(accent);
        mIST.registerCallbacks(new ISTCallbacks() {
            @Override
            public void onResult(IST.ISTResult result, Object usrTag) {
                Log.d(TAG, "Key:" + result.getKey());
                Log.d(TAG, "code:" + result.getCode());
                Log.d(TAG, "TaskId:" + result.getTaskId());
                Log.d(TAG, "Result:" + result.getResult());
                Log.d(TAG, "TaskStatus:" + result.getTaskStatus());
                Log.d(TAG, "Url:" + result.getUrl());
                Log.d(TAG, "tag:" + (String)usrTag);
                url = result.getUrl();
                taskID = result.getTaskId();
                String text = "Key:"+ result.getKey() + "\n"+"Result:"+ result.getResult() + "\n"+"Url:"+result.getUrl()+ "\n"+"TaskId:"+result.getTaskId()+ "\n";
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        chatOutputText.setText(text);

                        FileOutputStream fos2 = null;
                        try {
                            fos2 = new FileOutputStream("/sdcard/iflytek/ist_output.txt", true);
                            fos2.write(text.getBytes());
                            fos2.write("\r\n".getBytes());//写入换行
                            fos2.flush();
                            fos2.close();
                        } catch (Exception e) {
                            throw new RuntimeException(e);
                        }
                    }
                });
                isrun = false;
            }

            @Override
            public void onProcess(String process, Object usrTag) {
                Log.d(TAG, "onProcess:" + process);
            }

            @Override
            public void onError(IST.ISTError error, Object usrTag) {
                Log.d(TAG, "errorcode:" + error.getCode());
                Log.d(TAG, "sid:" + error.getSid());
                Log.d(TAG, "errortag:" + (String)usrTag);
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        String text = "onError code:"+error.getCode()+" msg:" + error.getErrMsg()+" sid:" + error.getSid() + "\n";
                        chatOutputText.setText(text);
                    }
                });
                isrun = false;
            }

        });
        if(!ismp){
            mIST.upload("/sdcard/iflytek/asr/cn.pcm","test_1","tag");
        }else{
            mIST.mpUpload("/sdcard/iflytek/asr/cn.pcm", "upload222", 5*1024*1024,"tag");
        }

    }


}
