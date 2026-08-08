package com.example.sparkchaindemo.ai.vc;

import android.os.Bundle;
import android.text.TextUtils;
import android.util.Log;
import android.view.View;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import com.example.sparkchaindemo.R;
import com.iflytek.sparkchain.core.vc.VC;
import com.iflytek.sparkchain.core.vc.VCCallbacks;

import java.io.File;
import java.io.FileOutputStream;

public class VCActivity extends AppCompatActivity {
    private static final String TAG = "VCActivity";
    TextView chatOutputText;
    ScrollView outputScroll;
    boolean isrun = false;
    VC mVc;
    String mToken;
    String taskId;
    String resId = "";
    int textSegId = -1;

    String text = "床前明月光，疑是地上霜，举头望明月，低头思故乡。";
    String audioUrl = "https://openres.xfyun.cn/xfyundoc/2026-02-26/bfd4a319-0535-42f6-98d7-2564cc3de06f/1772089259705/demo.wav";

    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.ai_vc);
        chatOutputText = findViewById(R.id.output_text);
        outputScroll = findViewById(R.id.output_scroll);
        init();
    }

    protected void init() {
        findViewById(R.id.get_token).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                getToken();
            }
        });
        findViewById(R.id.get_traintext).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                getTraintext();
            }
        });
        findViewById(R.id.create_task_add).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                createTaskAdd();
            }
        });
        findViewById(R.id.add_url).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                addUrl();
            }
        });
        findViewById(R.id.audio_submit_task).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                audioSubmitTask();
            }
        });
        findViewById(R.id.submit_task).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                submitTask();
            }
        });
        findViewById(R.id.get_taskresult_status).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                getTaskresultStatus();
            }
        });
        findViewById(R.id.start_tts).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                startTts();
            }
        });
    }

    private void appendToOutput(CharSequence text) {
        chatOutputText.append(text);
        scrollOutputToBottom();
    }

    private void scrollOutputToBottom() {
        outputScroll.post(() -> outputScroll.fullScroll(View.FOCUS_DOWN));
    }

    private void getToken() {
        if (isrun) return;
        isrun = true;
        taskId = "";
        textSegId = -1;
        if (mVc == null) {
            mVc = new VC();
        }
        mVc.registerCallbacks(mVCCallbacks);
        int ret = mVc.getToken("tag_getToken");
        Log.d(TAG, "getToken ret:" + ret);
        if(ret != 0)
        {
            Log.e(TAG,"getToken error! ret = " +ret);
            isrun = false;
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    appendToOutput("getToken error! ret = " +ret + "\n");
                }
            });
        }
    }

    private void getTraintext() {
        if (TextUtils.isEmpty(mToken)) {
            Toast.makeText(this, "token为空，请先申请token", Toast.LENGTH_SHORT).show();
            return;
        }
        if (isrun) return;
        isrun = true;
        if (mVc == null) {
            mVc = new VC();
        }
        mVc.registerCallbacks(mVCCallbacks);
        int ret = mVc.getTraninText(mToken, 5001, "tag_getTraintext");
        Log.d(TAG, "getTraninText ret:" + ret);
        if(ret != 0)
        {
            Log.e(TAG,"getTraninText error! ret = " +ret);
            isrun = false;
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    appendToOutput("getTraninText error! ret = " +ret + "\n");
                }
            });
        }
    }

    private void createTaskAdd() {
        if (TextUtils.isEmpty(mToken)) {
            Toast.makeText(this, "token为空，请先申请token", Toast.LENGTH_SHORT).show();
            return;
        }
        if (isrun) return;
        isrun = true;
        if (mVc == null) {
            mVc = new VC();
        }
        mVc.setParams(0, "engineVersion", "omni_v1");
        mVc.registerCallbacks(mVCCallbacks);
        int ret = mVc.taskAdd(mToken, "tag_taskAdd");
        Log.d(TAG, "taskAdd ret:" + ret);
        if(ret != 0)
        {
            Log.e(TAG,"taskAdd error! ret = " +ret);
            isrun = false;
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    appendToOutput("taskAdd error! ret = " +ret + "\n");
                }
            });
        }
    }

    private void addUrl() {
        if (TextUtils.isEmpty(mToken)) {
            Toast.makeText(this, "token为空，请先申请token", Toast.LENGTH_SHORT).show();
            return;
        }
        if (TextUtils.isEmpty(taskId)) {
            Toast.makeText(this, "taskId为空，请先创建任务", Toast.LENGTH_SHORT).show();
            return;
        }
        if (textSegId < 0) {
            Toast.makeText(this, "textSegId为空，请先获取训练文本", Toast.LENGTH_SHORT).show();
            return;
        }
        if (isrun) return;
        isrun = true;
        if (mVc == null) {
            mVc = new VC();
        }
        mVc.registerCallbacks(mVCCallbacks);
        int ret = mVc.addAudioUrl(mToken, audioUrl, taskId, textSegId, 5001, "tag_addUrl");
        Log.d(TAG, "addUrl ret:" + ret);
        if(ret != 0)
        {
            Log.e(TAG,"addUrl error! ret = " +ret);
            isrun = false;
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    appendToOutput("addUrl error! ret = " +ret + "\n");
                }
            });
        }
    }

    private void audioSubmitTask() {
        String audioPath = "/sdcard/iflytek/asr/vc_wq_35.pcm";
        if (TextUtils.isEmpty(mToken)) {
            Toast.makeText(this, "token为空，请先申请token", Toast.LENGTH_SHORT).show();
            return;
        }
        if (TextUtils.isEmpty(taskId)) {
            Toast.makeText(this, "taskId为空，请先创建任务", Toast.LENGTH_SHORT).show();
            return;
        }
        if (textSegId < 0) {
            Toast.makeText(this, "textSegId为空，请先获取训练文本", Toast.LENGTH_SHORT).show();
            return;
        }
        if (isrun) return;
        isrun = true;
        if (mVc == null) {
            mVc = new VC();
        }
        mVc.registerCallbacks(mVCCallbacks);
        int ret = mVc.submitWithAudio(mToken, audioPath, taskId, textSegId=35, 5001, "tag_audioSubmitTask");
        Log.d(TAG, "audioSubmitTask ret:" + ret);
        if(ret != 0)
        {
            Log.e(TAG,"audioSubmitTask error! ret = " +ret);
            isrun = false;
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    appendToOutput("audioSubmitTask error! ret = " +ret + "\n");
                }
            });
        }
    }

    private void submitTask() {
        if (TextUtils.isEmpty(mToken)) {
            Toast.makeText(this, "token为空，请先申请token", Toast.LENGTH_SHORT).show();
            return;
        }
        if (TextUtils.isEmpty(taskId)) {
            Toast.makeText(this, "taskId为空，请先创建任务", Toast.LENGTH_SHORT).show();
            return;
        }
        if (isrun) return;
        isrun = true;
        if (mVc == null) {
            mVc = new VC();
        }
        mVc.registerCallbacks(mVCCallbacks);
        int ret = mVc.submitTask(mToken, taskId, "tag_submitTask");
        Log.d(TAG, "submitTask ret:" + ret);
        if(ret != 0)
        {
            Log.e(TAG,"submitTask error! ret = " +ret);
            isrun = false;
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    appendToOutput("submitTask error! ret = " +ret + "\n");
                }
            });
        }
    }

    private void getTaskresultStatus() {
        if (TextUtils.isEmpty(mToken)) {
            Toast.makeText(this, "token为空，请先申请token", Toast.LENGTH_SHORT).show();
            return;
        }
        if (TextUtils.isEmpty(taskId)) {
            Toast.makeText(this, "taskId为空，请先创建任务", Toast.LENGTH_SHORT).show();
            return;
        }
        if (isrun) return;
        isrun = true;
        if (mVc == null) {
            mVc = new VC();
        }
        mVc.registerCallbacks(mVCCallbacks);
        int ret = mVc.getProcess(mToken, taskId, "tag_getTaskresultStatus");
        Log.d(TAG, "getTaskresultStatus ret:" + ret);
        if(ret != 0)
        {
            Log.e(TAG,"getTaskresultStatus error! ret = " +ret);
            isrun = false;
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    appendToOutput("getTaskresultStatus error! ret = " +ret + "\n");
                }
            });
        }
    }

    private void startTts() {
        Log.d(TAG, "startTts " + isrun);
        File file = new File("/sdcard/iflytek/vc_test.pcm");
        if (file.exists()) {
            file.delete();
        }
        if (TextUtils.isEmpty(resId)) {
            Toast.makeText(this, "resId为空，请查询任务状态获取音色id", Toast.LENGTH_SHORT).show();
            return;
        }
        if (isrun) return;
        isrun = true;
        if (mVc == null) {
            mVc = new VC();
        }
        mVc.setParams(1, "encoding", "utf8");
        mVc.setParams(1, "compress", "raw");
        mVc.setParams(1, "format", "plain");
        mVc.setParams(1, "sample_rate", 24000);
        mVc.registerCallbacks(mVCCallbacks);
        int ret = mVc.vcTTS(resId, text, "raw", 2, 0, "tag_vcTTS");
        Log.d(TAG, "startTts ret:" + ret);
        if(ret != 0)
        {
            Log.e(TAG,"startTts error! ret = " +ret);
            isrun = false;
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    appendToOutput("startTts error! ret = " +ret + "\n");
                }
            });
        }
    }

    VCCallbacks mVCCallbacks = new VCCallbacks() {
        @Override
        public void onResult(VC.VCResult result, Object usrTag) {
            Log.d(TAG, "key :" + result.getKey() + " status :" + result.getStatus() + " tag:" + usrTag);
            if (result.getKey().equals("tts")) {
                if (result.getStatus() == 2) {
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            appendToOutput("key :" + result.getKey() + "\n");
                        }
                    });
                }
            } else {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        appendToOutput("key :" + result.getKey() + "\n");
                    }
                });
            }

            if (result.getKey().equals("token")) {
                mToken = result.getToken();
                Log.d(TAG, "token :" + mToken);
                isrun = false;
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        appendToOutput("token :" + mToken + "\n");
                    }
                });
            } else if (result.getKey().equals("traintext")) {
                VC.TextSeg[] segs = result.getTextSegs();
                String info = "";
                if (segs.length > 0) textSegId = segs[0].getSegId();
                for (VC.TextSeg seg : segs) {
                    Log.d(TAG, "segId:" + seg.getSegId());
                    Log.d(TAG, "segText:" + seg.getSegText());
                    info += "segId:" + seg.getSegId() + "\n"
                            + "segText:" + seg.getSegText() + "\n"
                            + "segTextLan:" + seg.getSegTextLan() + "\n"
                            + "segSize:" + seg.getSegSize() + "\n";
                }
                String finalInfo = info;
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        appendToOutput(finalInfo);
                    }
                });
                isrun = false;
            } else if (result.getKey().equals("taskadd")) {
                taskId = result.getTaskId();
                Log.d(TAG, "taskId: " + taskId);
                isrun = false;
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        appendToOutput("taskId: " + taskId + "\n");
                    }
                });
            } else if (result.getKey().equals("audioadd")) {
                isrun = false;
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        appendToOutput("audioadd ok\n");
                    }
                });
            } else if (result.getKey().equals("tasksubmit")) {
                isrun = false;
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        appendToOutput("tasksubmit ok\n");
                    }
                });
            } else if (result.getKey().equals("submitwithaudio")) {
                isrun = false;
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        appendToOutput("submitwithaudio ok\n");
                    }
                });
            } else if (result.getKey().equals("taskresult")) {
                int status = result.getStatus();
                if (status == 2) {
                    resId = result.getAssetId();
                    Log.d(TAG, "train success, 音库id:" + result.getAssetId());
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            appendToOutput("音库id:" + result.getAssetId() + "\n");
                        }
                    });
                }
                isrun = false;
            } else if (result.getKey().equals("tts")) {
                byte[] audioData = result.getAudio();
                if (audioData != null && audioData.length > 0) {
                    try {
                        File file = new File("/sdcard/iflytek/vc_test.pcm");
                        FileOutputStream fos = new FileOutputStream(file, true);
                        fos.write(audioData);
                        fos.close();
                    } catch (Exception e) {
                        Log.e(TAG, "保存音频失败", e);
                        runOnUiThread(() -> appendToOutput("保存音频失败: " + e.getMessage() + "\n"));
                    }
                }
                if (result.getStatus() == 2) {
                    isrun = false;
                    runOnUiThread(() -> appendToOutput("24k16bit单声道音频已保存到: /sdcard/iflytek/vc_test.pcm\n"));
                }
            }
        }

        @Override
        public void onError(VC.VCError error, Object usrTag) {
            String message = "VCError error:" + error.getCode() + " msg:" + error.getMessage() + " tag:" + usrTag;
            Log.d(TAG, message);
            isrun = false;
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    appendToOutput(message+ "\n");
                }
            });
        }

        @Override
        public void onProcess(double dltotal, double dlnow, double ultotal, double ulnow, Object usrTag) {
            Log.d(TAG, "onProcess dltotal:" + dltotal + " dlnow:" + dlnow + " ultotal:" + ultotal + " ulnow:" + ulnow + " tag:" + usrTag);

        }
    };
}
