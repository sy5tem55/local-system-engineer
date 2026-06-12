llama.cpp
QWEN 3.6 27B Q5
~/llama.cpp/build/bin/llama-server \ 

  -models /home/sy5/models/Qwen3.6-27B-Q5_K_M.gguf \

  --ctx-size 65536 \

  --n-gpu-layers 99 \

  --jinja \

  --threads 8 \

  --host 0.0.0.0 \

  --port 8080

==-----  Open WebUI:==

source ~/owui/bin/activate
OPENAI_API_BASE_URL=http://localhost:8080/v1 OPENAI_API_KEY=none open-webui serve --port 3000

==------  Run Playwright :== 

source ~/owui/bin/activate
cd ~/owui/bin/
playwright run-server --port 3001


OPEN TERMINAL
open-terminal run




===============================================================================================

1. GPU + CUDA Initialization
CUDA0 : NVIDIA GeForce RTX 4090 (24563 MiB, 22988 MiB free)

Good.

Your RTX 4090 is detected correctly with ~23 GB free VRAM.

2. CPU Threading
n_threads = 8 (n_threads_batch = 8) / 20

This means:

llama.cpp is using:
8 inference threads
8 batch threads
your CPU exposes 20 logical cores to llama.cpp in this configuration

For a 14900KF this is conservative.

You could probably increase performance with:

-t 16 -tb 16

or even:

-t 20 -tb 20

depending on workload.

Not an error.

3. The First Important Warning
failed to fit params to free device memory:
n_gpu_layers already set by user to 99, abort

This is NOT a failure to load.

This means:

you manually specified:

-ngl 99

or equivalent

llama.cpp’s automatic VRAM fitting logic (-fit) tried to optimize GPU layer placement
but because you already forced GPU layers manually, it aborted the auto-fit step

This warning is harmless.

Recommendation

You should choose ONE strategy:

Strategy A — Manual GPU layers (your current setup)

Example:

-ngl 99

Disable fitting entirely:

-fit off

This avoids the warning.

Strategy B — Automatic fitting

Remove:

-ngl 99

and keep:

-fit

Then llama.cpp determines optimal offloading automatically.

For a 4090 + 27B Q5_K_M, auto-fit is usually preferable unless you are tuning aggressively.

4. Context Size Warning
n_ctx_seq (65536) < n_ctx_train (262144)

Important but not fatal.

Your model was trained for:

262144 context

but you launched with:

65536 context

Meaning:

you are only using 64K of the available 262K context window

This is normal because:

262K context on a 27B model is extremely VRAM intensive
even 64K is already huge
Important Performance Implication

64K context on Qwen 27B Q5_K_M likely consumes massive KV cache memory.

Even on a 4090:

generation speed may degrade significantly at large contexts
prompt ingestion becomes expensive
Recommended Realistic Context Sizes

For practical local inference:

Use Case	Recommended
General chat	8K–16K
RAG / coding	16K–32K
Huge document work	64K
Experimental	128K+

64K is already “serious.”

5. Warmup Phase
warming up the model with an empty run

Normal.

This precompiles CUDA graphs and kernels.

You can disable with:

--no-warmup

but warmup is usually beneficial.

6. Speculative Decoding Warning
speculative decoding will use checkpoints
no implementations specified for speculative decoding

This is probably the most misleading warning.

It means:

speculative decoding infrastructure is enabled
but no draft model was provided

So speculative decoding is effectively inactive.

No problem.

To actually use speculative decoding

You would need something like:

--draft-model smaller-model.gguf

Example:

Qwen 7B as draft
Qwen 27B as target
7. Prompt Cache
prompt cache is enabled, size limit: 8192 MiB

Good feature.

This caches KV states for repeated prompts.

Useful for:

chat
agents
system prompts
RAG

Consumes RAM.

8. KV Unified Warning
--cache-idle-slots requires --kv-unified, disabling

Meaning:

You enabled:

--cache-idle-slots

without:

--kv-unified

So llama.cpp disabled the feature automatically.

Harmless.

9. Chat Template Detection
thinking = 1

Important.

Your model template includes:

<think>

This means:

the model supports reasoning traces
likely Qwen reasoning mode

Some frontends may expose this poorly.

10. Final Status
server is listening on http://0.0.0.0:8080

Server is fully operational.

My Assessment

Your startup is fundamentally healthy.

The only things I would optimize:

Recommended Launch Cleanup

Something like:

./llama-server \
  -m /home/sy5/models/Qwen3.6-27B-Q5_K_M.gguf \
  -ngl 99 \
  -fit off \
  -c 32768 \
  -t 16 \
  -tb 16

Why:

disables meaningless fit warning
32K context is usually the sweet spot
more CPU threads for ingestion
cleaner startup
One More Important Thing

A 27B Q5_K_M at 64K context can approach VRAM exhaustion dynamically because KV cache grows during conversation.

You should monitor:

nvidia-smi

during:

long chats
RAG ingestion
agent loops

You may eventually hit:

CUDA OOM
fallback to CPU KV
severe slowdown

especially past ~40K effective context utilization.

Accuracy Assessment

Confidence: ~97%

The logs strongly indicate:

successful model initialization
successful CUDA offload
no fatal runtime issues

The warnings are configuration mismatches rather than instability indicators.



************************************************************************ B E N C H M A R K *******************************************************************************
You are ready to run a local llama-server:
If you launch llama-server, it will be listening at http://127.0.0.1:8080/ in your browser.


###################################################################
# You can now launch an optimized llama-server.                   #
# just run next lines in your terminal:                           #
###################################################################

LLAMA_BIN=/home/sy5/llama.cpp/build/bin
MODEL=/home/sy5/models/Qwen3.6-27B-Q5_K_M.gguf

 $LLAMA_BIN/llama-server --model $MODEL -t 13 --batch-size 6637 --ubatch-size 2875 -ngl 117  --override-tensor "blk\.\d+\.ffn_.*_exps\.=CPU"  --flash-attn

########################################################
# Benchmarking your OPTIMIZED configuration            #
# Let's run the following line on terminal:            #
########################################################

/home/sy5/llama.cpp/build/bin/llama-bench --model /home/sy5/models/Qwen3.6-27B-Q5_K_M.gguf -t 13 --batch-size 6637 --ubatch-size 2875 -ngl 117 --flash-attn 1 -n 128 -p 256 -r 6 --no-warmup --progress  --override-tensor "blk\.\d+\.ffn_.*_exps\.=CPU"

ggml_cuda_init: found 1 CUDA devices (Total VRAM: 24563 MiB):
  Device 0: NVIDIA GeForce RTX 4090, compute capability 8.9, VMM: yes, VRAM: 24563 MiB
| model                          |       size |     params | backend    | ngl | threads | n_batch | n_ubatch | fa | ot                    |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ------: | ------: | -------: | -: | --------------------- | --------------: | -------------------: |
llama-bench: benchmark 1/2: starting
llama-bench: benchmark 1/2: prompt run 1/6
llama-bench: benchmark 1/2: prompt run 2/6
llama-bench: benchmark 1/2: prompt run 3/6
llama-bench: benchmark 1/2: prompt run 4/6
llama-bench: benchmark 1/2: prompt run 5/6
llama-bench: benchmark 1/2: prompt run 6/6
| qwen35 27B Q5_K - Medium       |  19.52 GiB |    27.32 B | CUDA       | 117 |      13 |    6637 |     2875 |  1 | blk\.\d+\.ffn_.*_exps\.=CPU |           pp256 |     2487.33 ± 541.92 |
llama-bench: benchmark 2/2: starting
llama-bench: benchmark 2/2: generation run 1/6
llama-bench: benchmark 2/2: generation run 2/6
llama-bench: benchmark 2/2: generation run 3/6
llama-bench: benchmark 2/2: generation run 4/6
llama-bench: benchmark 2/2: generation run 5/6
llama-bench: benchmark 2/2: generation run 6/6
| qwen35 27B Q5_K - Medium       |  19.52 GiB |    27.32 B | CUDA       | 117 |      13 |    6637 |     2875 |  1 | blk\.\d+\.ffn_.*_exps\.=CPU |           tg128 |         39.77 ± 0.07 |

build: bb28c1fe2 (9281)

########################################################
# Compare your previous results with NON-OPTIMIZED case#
# Let's run the following line on terminal:            #
#                                                      #
# Look for results in column 't/s' (tokens/s)          #
# row tg128 --> reports on token  generation speed     #
# row pp256 --> reports on prompt processing speed     #
########################################################

/home/sy5/llama.cpp/build/bin/llama-bench --model /home/sy5/models/Qwen3.6-27B-Q5_K_M.gguf -n 128 -p 256 -r 6 --no-warmup --progress

ggml_cuda_init: found 1 CUDA devices (Total VRAM: 24563 MiB):
  Device 0: NVIDIA GeForce RTX 4090, compute capability 8.9, VMM: yes, VRAM: 24563 MiB
| model                          |       size |     params | backend    | ngl |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | --------------: | -------------------: |
llama-bench: benchmark 1/2: starting
llama-bench: benchmark 1/2: prompt run 1/6
llama-bench: benchmark 1/2: prompt run 2/6
llama-bench: benchmark 1/2: prompt run 3/6
llama-bench: benchmark 1/2: prompt run 4/6
llama-bench: benchmark 1/2: prompt run 5/6
llama-bench: benchmark 1/2: prompt run 6/6
| qwen35 27B Q5_K - Medium       |  19.52 GiB |    27.32 B | CUDA       |  99 |           pp256 |     2383.21 ± 704.91 |
llama-bench: benchmark 2/2: starting
llama-bench: benchmark 2/2: generation run 1/6
llama-bench: benchmark 2/2: generation run 2/6
llama-bench: benchmark 2/2: generation run 3/6
llama-bench: benchmark 2/2: generation run 4/6
llama-bench: benchmark 2/2: generation run 5/6
llama-bench: benchmark 2/2: generation run 6/6
| qwen35 27B Q5_K - Medium       |  19.52 GiB |    27.32 B | CUDA       |  99 |           tg128 |         39.39 ± 0.07 |

build: bb28c1fe2 (9281)



###################################################################
# You can now launch an optimized llama-server.                   #
# just run next lines in your terminal:                           #
###################################################################

LLAMA_BIN=/home/sy5/llama.cpp/build/bin
MODEL=/home/sy5/models/Qwen_Qwen3.6-27B-Q4_K_M.gguf

 $LLAMA_BIN/llama-server --model $MODEL -t 7 --batch-size 6377 --ubatch-size 4399 -ngl 129  --override-tensor "blk\.(?:[0-9]*[13579])\.ffn_.*_exps\.=CPU"  --flash-attn

########################################################
# Benchmarking your OPTIMIZED configuration            #
# Let's run the following line on terminal:            #
########################################################

/home/sy5/llama.cpp/build/bin/llama-bench --model /home/sy5/models/Qwen_Qwen3.6-27B-Q4_K_M.gguf -t 7 --batch-size 6377 --ubatch-size 4399 -ngl 129 --flash-attn 1 -n 128 -p 256 -r 6 --no-warmup --progress  --override-tensor "blk\.(?:[0-9]*[13579])\.ffn_.*_exps\.=CPU"

ggml_cuda_init: found 1 CUDA devices (Total VRAM: 24563 MiB):
  Device 0: NVIDIA GeForce RTX 4090, compute capability 8.9, VMM: yes, VRAM: 24563 MiB
| model                          |       size |     params | backend    | ngl | threads | n_batch | n_ubatch | fa | ot                    |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ------: | ------: | -------: | -: | --------------------- | --------------: | -------------------: |
llama-bench: benchmark 1/2: starting
llama-bench: benchmark 1/2: prompt run 1/6
llama-bench: benchmark 1/2: prompt run 2/6
llama-bench: benchmark 1/2: prompt run 3/6
llama-bench: benchmark 1/2: prompt run 4/6
llama-bench: benchmark 1/2: prompt run 5/6
llama-bench: benchmark 1/2: prompt run 6/6
| qwen35 27B Q4_K - Medium       |  16.74 GiB |    27.32 B | CUDA       | 129 |       7 |    6377 |     4399 |  1 | blk\.(?:[0-9]*[13579])\.ffn_.*_exps\.=CPU |           pp256 |     2523.54 ± 598.56 |
llama-bench: benchmark 2/2: starting
llama-bench: benchmark 2/2: generation run 1/6
llama-bench: benchmark 2/2: generation run 2/6
llama-bench: benchmark 2/2: generation run 3/6
llama-bench: benchmark 2/2: generation run 4/6
llama-bench: benchmark 2/2: generation run 5/6
llama-bench: benchmark 2/2: generation run 6/6
| qwen35 27B Q4_K - Medium       |  16.74 GiB |    27.32 B | CUDA       | 129 |       7 |    6377 |     4399 |  1 | blk\.(?:[0-9]*[13579])\.ffn_.*_exps\.=CPU |           tg128 |         45.71 ± 0.11 |

build: bb28c1fe2 (9281)

########################################################
# Compare your previous results with NON-OPTIMIZED case#
# Let's run the following line on terminal:            #
#                                                      #
# Look for results in column 't/s' (tokens/s)          #
# row tg128 --> reports on token  generation speed     #
# row pp256 --> reports on prompt processing speed     #
########################################################

/home/sy5/llama.cpp/build/bin/llama-bench --model /home/sy5/models/Qwen_Qwen3.6-27B-Q4_K_M.gguf -n 128 -p 256 -r 6 --no-warmup --progress

ggml_cuda_init: found 1 CUDA devices (Total VRAM: 24563 MiB):
  Device 0: NVIDIA GeForce RTX 4090, compute capability 8.9, VMM: yes, VRAM: 24563 MiB
| model                          |       size |     params | backend    | ngl |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | --------------: | -------------------: |
llama-bench: benchmark 1/2: starting
llama-bench: benchmark 1/2: prompt run 1/6
llama-bench: benchmark 1/2: prompt run 2/6
llama-bench: benchmark 1/2: prompt run 3/6
llama-bench: benchmark 1/2: prompt run 4/6
llama-bench: benchmark 1/2: prompt run 5/6
llama-bench: benchmark 1/2: prompt run 6/6
| qwen35 27B Q4_K - Medium       |  16.74 GiB |    27.32 B | CUDA       |  99 |           pp256 |     2432.37 ± 739.67 |
llama-bench: benchmark 2/2: starting
llama-bench: benchmark 2/2: generation run 1/6
llama-bench: benchmark 2/2: generation run 2/6
llama-bench: benchmark 2/2: generation run 3/6
llama-bench: benchmark 2/2: generation run 4/6
llama-bench: benchmark 2/2: generation run 5/6
llama-bench: benchmark 2/2: generation run 6/6
| qwen35 27B Q4_K - Medium       |  16.74 GiB |    27.32 B | CUDA       |  99 |           tg128 |         45.24 ± 0.15 |

build: bb28c1fe2 (9281)