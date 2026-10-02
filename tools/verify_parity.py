#!/usr/bin/env python3
"""Compare all logits from exported models against native streaming C++ inference."""
import argparse, json, subprocess, tempfile
from pathlib import Path
import numpy as np
import torch
from hybrid_model import HybridTiny, export
from train_tiny import TinyEdge, export as export_v2


def compare(executable, model, filename, payload, kernel, directory):
    source, output = directory / "tokens.bin", directory / "logits.f32"
    source.write_bytes(payload)
    subprocess.run([str(executable), str(filename), str(source), str(output), kernel], check=True, capture_output=True)
    native = np.fromfile(output, dtype="<f4").reshape(len(payload), 256)
    with torch.inference_mode():
        reference = model(torch.tensor([list(payload)], dtype=torch.long))[0].numpy()
    error = float(np.max(np.abs(native-reference)))
    if not np.allclose(native, reference, rtol=3e-5, atol=3e-5):
        raise AssertionError(f"{filename.name}/{kernel}: logits mismatch, max error {error}")
    return dict(model=filename.name, kernel=kernel, tokens=len(payload), compared_values=int(native.size), max_absolute_error=error, passed=True)


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--checkpoint",type=Path,default=Path("models/hybrid_tiny.pt"))
    ap.add_argument("--out",type=Path,default=Path("results/parity.json"));args=ap.parse_args()
    torch.set_num_threads(1);torch.manual_seed(829);results=[]
    with tempfile.TemporaryDirectory() as temp:
        temp=Path(temp)
        cases=[("hybrid_odd.edge",HybridTiny(17,31,7,5,3), bytes(range(63))),
               ("hybrid_all_bytes.edge",HybridTiny(32,64,16,16,1),bytes(range(256))+"ação e memória".encode()),
               ("legacy.edge",TinyEdge(16,32,2),"teste de paridade código".encode())]
        if args.checkpoint.exists():
            data=torch.load(args.checkpoint, map_location="cpu", weights_only=True)
            model=HybridTiny(**data["config"]);model.load_state_dict(data["state_dict"])
            cases.append(("trained.edge",model,"usuario: para que serve a memória?\nassistente:".encode()))
        for name,model,tokens in cases:
            model.eval();file=temp/name
            (export_v2 if isinstance(model,TinyEdge) else export)(model,file)
            for kernel in ("scalar","lookup2","auto"):
                results.append(compare(args.binary.resolve(),model,file,tokens,kernel,temp))
        # The training path must be causal and every parameter must receive a finite gradient.
        model=HybridTiny(16,32,8,8,2);x=torch.randint(0,256,(2,25));z=model(x)
        torch.testing.assert_close(z[:,:10],model(x[:,:10]),rtol=3e-5,atol=3e-5)
        torch.nn.functional.cross_entropy(z.flatten(0,1),torch.randint(0,256,(50,))).backward()
        for name,param in model.named_parameters():
            if param.grad is None or not torch.isfinite(param.grad).all() or param.grad.abs().sum().item()==0:
                raise AssertionError(f"missing/invalid/zero gradient: {name}")
    report=dict(logit_cases=results,causality_passed=True,all_parameters_receive_gradients=True)
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
