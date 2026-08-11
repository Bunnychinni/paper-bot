import sys,math
def cp(x): return math.ceil(x*100-1e-9)/100
def rt(prem,n,sp): return (0.055)*n*2+cp(0.00279*n)+cp(20.6e-6*prem*100*n)+prem*100*n*sp/100
def guess(p): return 15. if p<.30 else 10. if p<.75 else 8. if p<1.5 else 6. if p<3 else 4.
def theta(d): return 1-math.sqrt(max(d-1,0)/d) if d>0 else 1.
a=sys.argv[1:]
def g(k,d):
    return float(a[a.index(k)+1]) if k in a else d
if not a or a[0]=="compare":
    s=g("--spot",50.)
    print("\n  SAME $300, FOUR STRUCTURES  (spot $%.2f)\n"%s)
    print("  %-26s%11s%12s%10s%11s"%("structure","cost drag","max gain","max loss","ruin risk"))
    print("  "+"-"*68)
    for nm,p,mg,ml,rk in [("Long OTM call (5% OTM)",.35,"unlimited","100%","high"),
                          ("Long ATM call",1.80,"unlimited","100%","high"),
                          ("Vertical debit spread",.95,"capped","capped","moderate"),
                          ("Buy 6 shares of stock",None,"unlimited","~stock","low")]:
        if p is None: d="0.12%"
        else:
            n=max(1,int(300/(p*100))); d="%.1f%%"%(100*rt(p,n,guess(p))/(p*100*n))
        print("  %-26s%11s%12s%10s%11s"%(nm,d,mg,ml,rk))
    print("\n  6 shares of a $50 stock costs 0.12% round trip vs 8-15% for options,")
    print("  and cannot go to zero in a week.\n")
elif a[0]=="payoff":
    s,k,p,d=g("--spot",50.),g("--strike",52.),g("--prem",.35),g("--dte",7)
    sp=g("--spread-pct",0) or guess(p); n=int(g("--contracts",0)) or max(1,int(300/(p*100)))
    deb=p*100*n; c=rt(p,n,sp); be=k+p+c/(100*n); th=theta(d)
    print("\n  LONG CALL  spot $%.2f  strike $%.2f  prem $%.2f  %dx  %dDTE"%(s,k,p,n,d))
    print("  debit          $%8.2f"%deb)
    print("  round-trip cost $%7.2f  (%.1f%% of debit)"%(c,100*c/deb))
    print("  MAX LOSS       $%8.2f  = 100%% of debit + cost"%(deb+c))
    print("  break-even     $%8.2f  spot must move %+.2f%%"%(be,100*(be/s-1)))
    print("  theta ~%.1f%%/day = $%.2f/day doing nothing"%(100*th,deb*th))
    print("  3 idle days -> ~$%.2f gone\n"%(deb*(1-(1-th)**3)))
elif a[0]=="spread":
    s,lo,hi,deb,d=g("--spot",50.),g("--long",51.),g("--short",54.),g("--debit",.95),g("--dte",14)
    sp=g("--spread-pct",0) or guess(deb); n=int(g("--contracts",0)) or max(1,int(300/(deb*100)))
    net=deb*100*n; c=rt(deb,n,sp)*1.6; w=abs(hi-lo)
    mg=(w-deb)*100*n-c; be=lo+deb+c/(100*n)
    print("\n  VERTICAL  long $%.2f / short $%.2f  %dx  %dDTE"%(lo,hi,n,d))
    print("  net debit      $%8.2f"%net)
    print("  MAX LOSS       $%8.2f  <- CAPPED"%(net+c))
    print("  MAX GAIN       $%8.2f  <- also capped"%mg)
    print("  risk:reward    1 : %.2f"%(mg/(net+c)))
    print("  break-even     $%8.2f  spot must move %+.2f%%"%(be,100*(be/s-1)))
    print("  break-even win rate  %.1f%%\n"%(100/(1+mg/(net+c))))
