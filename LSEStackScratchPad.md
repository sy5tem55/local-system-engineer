PFSENSE Network engineer
Knowledge base: Access at the official documentation URL so it can stay uptodate
Access to the lastest CVE to stay on top of 0days


LSE System Admin Terminal v1.5.5 deployed
Elaborate and explain, I am not clear the action I have to take to implement: read_file PRIVILEGED PATH BEHAVIOUR Add "do NOT try cat/python/base64 workarounds"

Write prompt 0.5.2

work on a skill for LSE to check ports in use before starting work on deployment

LSE works better with /nothink



http://localhost:3002/dashboards results in server error, also there is Graphana dashboard troubleshooting




https://docs.openwebui.com/features/administration/webhooks/

LSE seems to regularly stop work after 16 tool calls




add preset 12 to load Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf, preset 9 throws:0.00.510.178 E srv    load_model: [spec] failed to measure MTP context memory: failed to create llama_context from model
so it need to be run without MTP, also check if there are duplicate presets 






0.00.510.206 I common_init_result: fitting params to device memory ...

0.00.510.206 I common_init_result: (for bugs during this step try to reproduce them with -fit off, or provide --verbose logs if the bug only occurs with -fit on)

0.16.136.542 W llama_context: n_ctx_seq (32768) < n_ctx_train (262144) -- the full capacity of the model will not be utilized

0.16.186.864 I common_init_from_params: warming up the model with an empty run - please wait ... (--no-warmup to disable)

0.16.369.206 I srv    load_model: creating MTP draft context against the target model '/home/sy5/models/Qwopus3.6-35B-A3B-v1-Q4_K_M.gguf'

0.16.369.223 W llama_init_from_model: context type MTP requested but model doesn't contain MTP layers

0.16.369.223 E srv    load_model: failed to create MTP context

0.16.369.224 I srv    operator(): operator(): cleaning up before exit...

0.16.370.011 E srv  llama_server: exiting due to model loading error


