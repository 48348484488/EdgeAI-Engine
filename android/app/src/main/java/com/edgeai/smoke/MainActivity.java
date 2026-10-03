package com.edgeai.smoke;

import android.app.Activity;
import android.os.Bundle;
import android.util.Log;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private static final String TAG = "EDGEAI_SMOKE";

    static {
        System.loadLibrary("edgeai_android_jni");
    }

    private static native String nativeAsk(String prompt);

    private void execute(EditText prompt, TextView output) {
        try {
            long startNs = System.nanoTime();
            String result = nativeAsk(prompt.getText().toString());
            long elapsedUs = (System.nanoTime() - startNs) / 1000L;
            String measured = result + "\n[elapsed_us=" + elapsedUs + "]";
            output.setText(measured);
            Log.i(TAG, measured.replace('\n', ' '));
        } catch (Throwable error) {
            String result = "Erro: " + error;
            output.setText(result);
            Log.e(TAG, result, error);
        }
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = (int)(16 * getResources().getDisplayMetrics().density);
        root.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText("EdgeAI Android smoke");
        title.setTextSize(20f);

        EditText prompt = new EditText(this);
        prompt.setSingleLine(false);
        prompt.setText("Subtract 17 from 42");

        Button ask = new Button(this);
        ask.setText("Executar");

        TextView output = new TextView(this);
        output.setTextIsSelectable(true);

        root.addView(title, new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        root.addView(prompt, new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        root.addView(ask, new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        root.addView(output, new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        ask.setOnClickListener(v -> execute(prompt, output));
        setContentView(root);

        String automatedPrompt = getIntent().getStringExtra("prompt");
        if (automatedPrompt != null) {
            prompt.setText(automatedPrompt);
            execute(prompt, output);
        }
    }
}
