"""Plot only a completed v2 run, into a new folder within that run.

    PYTHONPATH=src .venv/bin/python -m eval.plotting.performance_rerun_v2 --run PATH

Never publishes to eval/results or overwrites any existing figure. Both time
definitions are exported, explicitly named, without assuming monotonic trends.
"""

import argparse
from pathlib import Path
import json
import math
import uuid

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, ScalarFormatter
import numpy as np
import pandas as pd

STYLE={"font.family":"serif", "font.serif":["Times New Roman","DejaVu Serif"],
       "mathtext.fontset":"stix", "font.size":8,"axes.labelsize":8.5,
       "xtick.labelsize":7,"ytick.labelsize":7,"legend.fontsize":8,
       "axes.linewidth":.6,"pdf.fonttype":42}
SERIES=(("compile","Compilation","#2171b5","o","-"),
        ("setup","Setup","#8c2d26","s","--"),
        ("witness","Witness encoding","#54278f","^",":"),
        ("prove","Proof generation","#005a32","D","-."))
FAMILIES=(("sequence","#2171b5","o","-"),("choice","#8c2d26","s","--"),
          ("parallel","#005a32","^","-."),("loop","#54278f","D",":"))
LABELS={"bpic13cp":"BPI 2013","rtfm":"Road Traffic Fines","sepsis":"Sepsis","hospital":"Hospital Billing"}


def axes_style(ax):
    ax.spines[["top","right"]].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(True,which="major",linestyle="--",linewidth=.4,alpha=.35)


def log_limits(ax, mean, sd):
    lower=np.asarray(mean)-np.asarray(sd)
    upper=np.asarray(mean)+np.asarray(sd)
    if (lower<=0).any():
        raise ValueError("Mean minus SD is non-positive; do not silently clip a logarithmic error bar")
    ax.set_yscale("log")
    ax.set_ylim(lower.min()*.6, upper.max()*1.8)
    lo=math.ceil(math.log10(lower.min()*.6)); hi=math.floor(math.log10(upper.max()*1.8))
    ax.set_yticks([10.0**n for n in range(lo,hi+1)])


def capacity_figure(frame, scope):
    frame=frame[frame.stage.isin([s[0] for s in SERIES])]
    fig,axes=plt.subplots(1,2,figsize=(12.2/2.54,4.5/2.54))
    for stage,label,color,marker,style in SERIES:
        g=frame[frame.stage==stage].sort_values("alignment_capacity")
        for ax,metric,unit in ((axes[0],scope+"_time","s"),(axes[1],"mem","mb")):
            ax.errorbar(g.alignment_capacity,g[f"{metric}_mean_{unit}"],yerr=g[f"{metric}_sd_{unit}"],
                        label=label,color=color,marker=marker,linestyle=style,
                        linewidth=1,markersize=3.2,markerfacecolor="white",capsize=2.5,elinewidth=.8)
    for ax in axes:
        axes_style(ax)
        ax.set_xticks(sorted(frame.alignment_capacity.unique()))
        ax.set_xlim(18,398)
        ax.get_xticklabels()[0].set_ha("right")
        ax.get_xticklabels()[1].set_ha("left")
    log_limits(axes[0],frame[f"{scope}_time_mean_s"],frame[f"{scope}_time_sd_s"])
    axes[0].set_ylabel("Time (s)")
    axes[1].set_ylabel("Memory (MB)")
    high=(frame.mem_mean_mb+frame.mem_sd_mb).max()
    axes[1].set_ylim(-.03*high,1.12*high)
    axes[1].yaxis.set_major_locator(MaxNLocator(nbins=5))
    fig.legend(*axes[0].get_legend_handles_labels(),loc="upper center",ncol=2,frameon=False)
    fig.supxlabel(r"Alignment capacity $B_\gamma$ (moves)",fontsize=9,y=.04)
    fig.subplots_adjust(left=.12,right=.975,bottom=.26,top=.70,wspace=.55)
    return fig


def comparison_figure(frame):
    fig,ax=plt.subplots(figsize=(12.2/2.54,4.5/2.54))
    ticks,labels=[],[]
    for j,(dataset,title) in enumerate(LABELS.items()):
        part=frame[frame.dataset==dataset]
        def rank(index):
            role=part[part.case_index==index].roles.iloc[0].split("+")
            return 0 if "short" in role else 1 if "median" in role else 2
        ids=sorted(part.case_index.unique(),key=rank)
        x=np.arange(len(ids))+j*4
        for method,offset,color in (("PM4Py",-.19,"#8c2d26"),("zkALIGN",.19,"#2171b5")):
            g=part[part.method==method].set_index("case_index").loc[ids]
            ax.bar(x+offset,g.time_mean_s,width=.34,color=color,yerr=g.time_sd_s,
                   label=("Plaintext (PM4Py)" if method=="PM4Py" else method) if j==0 else None,
                   error_kw={"elinewidth":.7,"capsize":1.8,"capthick":.7})
        for i,pos in zip(ids,x):
            row=part[part.case_index==i].iloc[0]
            ticks.append(pos);labels.append(f"{['Short','Median','Long'][rank(i)]}\n({int(row.alignment_length)})")
        ax.text(x.mean(),-.50,title,ha="center",va="top",transform=ax.get_xaxis_transform(),fontsize=7.5)
    axes_style(ax)
    log_limits(ax,frame.time_mean_s,frame.time_sd_s)
    ax.set_xticks(ticks,labels)
    ax.set_ylabel("Time (s)")
    ax.legend(loc="upper center",bbox_to_anchor=(.5,1.36),ncol=2,frameon=False)
    fig.subplots_adjust(left=.115,right=.99,bottom=.35,top=.80)
    return fig


def model_figure(frame,scope):
    frame=frame[frame.stage=="prove"]
    fig,axes=plt.subplots(1,2,figsize=(12.2/2.54,4.5/2.54))
    for family,color,marker,style in FAMILIES:
        g=frame[frame.family==family].sort_values("activities")
        kw=dict(color=color,marker=marker,linestyle=style,markersize=3,linewidth=.9,
                markerfacecolor="white",label=family.capitalize())
        axes[0].plot(g.activities,g.constraints,**kw)
        axes[1].errorbar(g.activities,g[f"{scope}_time_mean_s"],yerr=g[f"{scope}_time_sd_s"],capsize=2,**kw)
    for ax in axes:
        axes_style(ax);ax.set_xticks([5,10,20,30,40,50]);ax.set_xlim(2,53)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    formatter=ScalarFormatter(useMathText=True);formatter.set_powerlimits((0,0))
    axes[0].yaxis.set_major_formatter(formatter)
    axes[0].set_ylabel("Constraints")
    axes[1].set_ylabel("Proof time (s)")
    fig.legend(*axes[0].get_legend_handles_labels(),loc="upper center",ncol=4,frameon=False,
               columnspacing=1.1,handlelength=1.4)
    fig.supxlabel("Number of visible activities",fontsize=8.5,y=.04)
    fig.subplots_adjust(left=.12,right=.99,bottom=.26,top=.75,wspace=.48)
    return fig


def generate(run):
    run=Path(run).resolve()
    if not (run/"complete.json").is_file():
        raise ValueError("Run is incomplete; inspect raw results before plotting")
    manifest=json.loads((run/"manifest.json").read_text())
    count=manifest["main_threads"]
    results=run/"results"
    # Validate every selected table before creating any output.
    frames={}
    for name in ("capacity_performance","plaintext_comparison","model_scalability"):
        path=results/f"{name}.csv"
        if path.exists():
            frame=pd.read_csv(path)
            frame=frame[frame.threads==count].copy()
            if frame.empty or not frame.complete.eq(True).all():
                raise ValueError(f"Incomplete data in {path}")
            frames[name]=frame
    out=run/("plots-"+uuid.uuid4().hex[:8]);out.mkdir()
    paths=[]
    with plt.rc_context(STYLE):
        for name,frame in frames.items():
            for scope in ("operation","worker"):
                if name=="capacity_performance":fig=capacity_figure(frame,scope)
                elif name=="model_scalability":fig=model_figure(frame,scope)
                else:fig=comparison_figure(frame[frame.time_scope==scope])
                tag="operation_time" if scope=="operation" else "complete_process_time"
                path=out/f"caise_{name}_{tag}.pdf"
                fig.savefig(path);plt.close(fig);paths.append(path)
    (out/"MEASUREMENT_SCOPES.txt").write_text(
        "operation_time: internally timed computation, excluding startup, input loading and serialization.\n"
        "complete_process_time: launch through blocking wait4 return, including loaded inputs and output.\n"
        "Comparison complete-process totals sum alignment, witness and proving processes; setup and verification excluded.\n"
        "Memory: whole-process OS peak RSS in decimal MB for both time variants.\n"
        f"Thread configuration for plotted Go stages: GOMAXPROCS={count}.\n"
        f"All error bars are sample standard deviations over {manifest['repetitions']} repetitions.\n")
    return paths


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path,required=True)
    args=parser.parse_args()
    for path in generate(args.run):print(path)
