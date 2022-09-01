#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar  7 20:26:51 2021

@author: blau
"""

from ib_insync import IB, Stock, Option, util
import os
import sys
import time
from datetime import datetime
#import sys
from itertools import compress
import asciichart
import numpy
import argparse

def getArgs(argv):
    '''
    get args from command line sys.argv[1:]
    '''
    parser = argparse.ArgumentParser(description="Setup a surface calculation")
    # electronic structure arguments
    parser.add_argument('-s',help="stock ticker (string)",default='TKR')
    parser.add_argument('-o',help="option strike range: (min,max,x % 1 result)",default='50,800,1')
    parser.add_argument('-c',help="calendar date",default=0,type=int)
    
    args = parser.parse_args(argv)
    
    args.o = [float(e) for e in args.o.split(',')]
    
    return args

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    
def graceful_exit(ib,contracts):
    ib.sleep()
    for c in contracts:
        ib.cancelMktData(c)
    ib.cancelMktData(TKR)
    ib.disconnect()
    
def nan2zero(list_with_nans):
    return [0 if util.isNan(e) else e for e in list_with_nans]

def get_oi(tickers):
    '''
    get open interest
    pcoi : total open interest
    poi : put open interest
    coi : call open interest
    missing open interest is set to 1
    '''
    pcoi = numpy.nan_to_num([t.putOpenInterest if t.putOpenInterest else t.callOpenInterest for t in tickers])
    pcoi[pcoi==0] = 1
    poi = pcoi[pm]
    coi = pcoi[cm]
    return pcoi, poi, coi

if __name__ == '__main__':
    
    if any('SPYDER' in name for name in os.environ):
        util.startLoop()
    #util.logToConsole()
    
    args = getArgs(sys.argv[1:])
    
    ib = IB()
    start_time = datetime.now()
    ib.connect('127.0.0.1', 7496, clientId=int(start_time.strftime('%H%M%S')), readonly=True)
    
    # live data
    ib.reqMarketDataType(1)
    
    TKR = Stock(symbol=args.s,exchange='SMART',currency='USD')
    ib.qualifyContracts(TKR)
    
    chains = ib.reqSecDefOptParams(TKR.symbol,'',TKR.secType,TKR.conId)
    chain = [c for c in chains if c.exchange == 'SMART'][0]
    
    strikes = [strike for strike in chain.strikes
        if strike % args.o[2] == 0
        and strike >= args.o[0]
        and strike <= args.o[1]]
    expirations = [sorted(exp for exp in chain.expirations)[args.c]]
    rights = ['P', 'C']
    #rights = ['C']
    contracts = [Option(args.s,expiration,strike,right,'SMART',tradingClass=args.s)
            for right in rights
            for expiration in expirations
            for strike in strikes]
    strikes_label = [str(e.strike)+e.right for e in contracts]
    
    before_qualify = len(contracts) 
    contracts = ib.qualifyContracts(*contracts)
    print(f'Before {before_qualify} After {len(contracts)}')
    
    tickers = [ib.reqMktData(contract=c,genericTickList='101') for c in contracts]
    pm = [t.contract.right == 'P' for t in tickers]
    cm = [not m for m in pm]

    print('Grabbing open interest / start volume ...',end='') 
    t = time.time()
    for a in range(10):
        ib.sleep(1)
        pcoi, poi, coi = get_oi(tickers)
        ovopen = numpy.nan_to_num([t.volume for t in tickers])
    print(f': Elapsed time {time.time() - t}')
    
    vol_cfg = {'height':22}
    vol_cfg['colors'] = []
    vol_cfg['format'] = '{:6.2f}'
    vol_cfg['min'] = 0
    vol_cfg['tips'] = 1000
    vol_cfg['linestyle'] = 'bar'
    width = 8 # x-axis offset
    TKR_axis = numpy.asarray([c.strike for c in compress(contracts,pm)])
    strikes_axis = []
    #for a in range(max([len(str(e).split('.')[0]) for e in TKR_axis])):
    #    strikes_axis.append([str(e).split('.')[0][a] if a<len(str(e).split('.')[0]) else ' ' for e in TKR_axis])
    for a in range(3):
        strikes_axis.append([str(e)[a] for e in TKR_axis])
    
    tickers = [ib.reqMktData(TKR)] + tickers
    ib.sleep(1)
    
    sleep = 2
    periodm = int(6.5*60) # entire day's trading period
    periods = periodm*60
    sleep_reset = periods//sleep+1
    loop_counter = 0
    svhist = numpy.zeros(sleep_reset)
    svhist[:] = tickers[0].volume*100
    ovhist = numpy.zeros((sleep_reset,len(ovopen)))
    ovhist[:] = ovopen
    odhist = numpy.zeros(ovhist.shape)
    oihist = numpy.zeros(ovhist.shape)
    oihist[:] = pcoi
    dodhist = numpy.diff(odhist,axis=0)
    doihist = numpy.zeros(dodhist.size)
    dhds = numpy.zeros(sleep_reset)
    
    def report_over_period(period_str,ind_last=None):
        if ind_last is None:
            svlast = 0
            ovlast = 0
            oilast = pcoi
        else:
            svlast = svhist[ind_last]
            ovlast = ovhist[ind_last]
            oilast = oihist[ind_last]
            
        # stock volume
        dsv = svhist[0] - svlast
        
        # option volume screener
        dv = vtick - ovlast
        dpv = numpy.sum(dv[pm])
        dcv = numpy.sum(dv[cm])
        
        doi = oihist[0] - oilast
        dpvoi = numpy.sum(doi[pm])
        dcvoi = numpy.sum(doi[cm])
        
        # delta hedging
        
        if ind_last is None:
            ddh = numpy.sum(odhist[0]*oihist[0])*100
        else:
            ddh = numpy.trapz(dhds[1:ind_last-1],dx=sleep)
        
        print(f'{period_str:<17s} pv={dpv:>5.0f} cv={dcv:>5.0f} pv/cv={dpv/dcv:>5.3f} Δv={dpvoi:>5.0f} Δc={dcvoi:>5.0f} δh={ddh:>10,.0f} vol={dsv:>10,.0f}')
        return dpv, dcv, dpvoi, dcvoi, ddh, dsv
    
    print('Begin live reporting ... ')
    try:
        while True:
            ib.sleep(sleep)
            
            TKRlast = tickers[0].last
            TKRplot = abs(TKR_axis-TKRlast).argmin()
            # option volume scanning
            vtick = numpy.nan_to_num([t.volume for t in tickers[1:]])
            dtick = numpy.nan_to_num([t.modelGreeks.delta if t.modelGreeks else 0 for t in tickers[1:]])
            
            svhist = numpy.roll(svhist,1)
            svhist[0] = tickers[0].volume*100
            
            ovhist = numpy.roll(ovhist,1,axis=0)
            ovhist[0] = vtick
            
            odhist = numpy.roll(odhist,1,axis=0)
            odhist[0] = dtick
            
            oihist = numpy.roll(oihist,1,axis=0)
            ind = vtick < pcoi
            oihist[0] = vtick
            oihist[0,ind] = pcoi[ind]
            
            dhds = numpy.roll(dhds,1)
            dhds[0] = numpy.sum((odhist[0] - odhist[1])*oihist[0])*100/sleep
            
            # check for unusual volume
            
        
            # plot
            os.system('clear')
            m_elapsed = loop_counter*2//60
            print(f"{datetime.now().astimezone(tz=None).strftime('%I:%M:%S %p')}, poi/coi={sum(poi)/sum(coi):2.2f}, time_elapsed={m_elapsed//60}h{m_elapsed % 60}m")
            pvtick = vtick[pm]
            ind1 = pvtick>poi
            cvtick = vtick[cm]
            ind2 = cvtick>coi
            vtickoi = numpy.c_[pvtick/poi,cvtick/coi].T
            vol_cfg['format'] = '{:6.1f}'
            vol_cfg['max'] = numpy.max(vtickoi)*1.05
            vol_cfg['colors'] = [asciichart.red,asciichart.green]
            print(asciichart.plot(vtickoi,vol_cfg))
            # x-axis
            for a,sa in enumerate(strikes_axis):
                print(' '*width,end='')
                for b,saa in enumerate(sa):
                    strike_char = saa
                    if ind1[b] and a == 0: # color put volume > poi
                        strike_char = asciichart.colored(strike_char,asciichart.red)
                    if ind2[b] and a == 1:
                        strike_char = asciichart.colored(strike_char,asciichart.green)
                    print(strike_char,end='')
                print()
            print(' '*width + ' '*TKRplot + '*' + f'{TKRlast:>5.2f}')
            ovoi = oihist[0] - pcoi
            ovoi = numpy.c_[ovoi[pm],ovoi[cm]].T
            vol_cfg['format'] = '{:6.0f}'
            vol_cfg['max'] = numpy.nanmax(ovoi)*1.05
            vol_cfg['colors'] = [asciichart.red,asciichart.green]
            print(asciichart.plot(ovoi,vol_cfg))

            # print out signals for total intraday, and last 10, 5, and 1 minutes
            report_over_period(f"Intra|{start_time.astimezone(tz=None).strftime('%I:%M:%S %p')}")
            
            ind_last = (15*60//sleep)
            report_over_period('15 min',ind_last)
            
            ind_last = (10*60//sleep)
            report_over_period('10 min',ind_last)
            
            ind_last = (5*60//sleep)
            report_over_period('5 min',ind_last)
            
            ind_last = (3*60//sleep)
            report_over_period('3 min',ind_last)
            
            ind_last = (1*60//sleep)
            report_over_period('1 min',ind_last)
            
            if not dtick.all():
                print(f"Delta incomplete! {numpy.array(strikes_label)[(dtick==0).nonzero()[0]]}")
                
            loop_counter += 1
            if loop_counter*sleep % 60 == 0:
                # refresh oi if it's not properly grabbed the first time
                pcoi, poi, coi = get_oi(tickers[1:])
            if loop_counter == sleep_reset:
                loop_counter = 0
            
    except (KeyboardInterrupt, SystemExit):
        graceful_exit(ib,contracts)
        print('Live reporting canceled, canceling mktData and disconnecting')
    
'''
tickTypeFound = False
while not tickTypeFound:
    ib.sleep()
    if t.ticks:
        vtick = [v for v in t.ticks if v.tickType==8]
        if vtick:
            tickTypeFound = True
'''
    