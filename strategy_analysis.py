import csv
from datetime import datetime

DATA_FILE = 'QQQ_15min_2023-2025.csv'

# parameters
SHORT_WINDOW = 20
LONG_WINDOW = 50

class Trade:
    def __init__(self, time, price, position):
        self.time = time
        self.price = price
        self.position = position
        self.exit_time = None
        self.exit_price = None

    def close(self, time, price):
        self.exit_time = time
        self.exit_price = price

    def pnl(self):
        if self.exit_price is None:
            return 0.0
        if self.position == 1:
            return self.exit_price / self.price - 1
        else:
            return self.price / self.exit_price - 1


def read_data(path):
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            row['Datetime'] = datetime.strptime(row['Datetime'], '%Y-%m-%d %H:%M:%S')
            row['Open'] = float(row['Open'])
            row['High'] = float(row['High'])
            row['Low'] = float(row['Low'])
            row['Close'] = float(row['Close'])
            row['Volume'] = float(row['Volume'])
            rows.append(row)
    return rows


def run_strategy(rows):
    closes = []
    position = 0
    equity = 1.0
    last_close = rows[0]['Close']
    trades = []
    eq_curve = []
    for row in rows:
        close = row['Close']
        closes.append(close)
        if len(closes) > LONG_WINDOW:
            short_ma = sum(closes[-SHORT_WINDOW:]) / SHORT_WINDOW
            long_ma = sum(closes[-LONG_WINDOW:]) / LONG_WINDOW
            prev_short_ma = sum(closes[-SHORT_WINDOW-1:-1]) / SHORT_WINDOW
            prev_long_ma = sum(closes[-LONG_WINDOW-1:-1]) / LONG_WINDOW
            # cross detection
            cross_up = prev_short_ma <= prev_long_ma and short_ma > long_ma
            cross_dn = prev_short_ma >= prev_long_ma and short_ma < long_ma
            if position == 0:
                if cross_up:
                    position = 1
                    trades.append(Trade(row['Datetime'], close, position))
                elif cross_dn:
                    position = -1
                    trades.append(Trade(row['Datetime'], close, position))
            elif position == 1:
                if cross_dn:
                    trades[-1].close(row['Datetime'], close)
                    position = -1
                    trades.append(Trade(row['Datetime'], close, position))
            elif position == -1:
                if cross_up:
                    trades[-1].close(row['Datetime'], close)
                    position = 1
                    trades.append(Trade(row['Datetime'], close, position))
        # update equity
        ret = position * (close / last_close - 1)
        equity *= (1 + ret)
        last_close = close
        eq_curve.append((row['Datetime'], equity))
    # close last trade
    if trades and trades[-1].exit_price is None:
        trades[-1].close(rows[-1]['Datetime'], rows[-1]['Close'])
    return eq_curve, trades


def buy_and_hold(rows):
    equity = 1.0
    eq_curve = []
    last = rows[0]['Close']
    for row in rows:
        close = row['Close']
        equity *= (close / last)
        last = close
        eq_curve.append((row['Datetime'], equity))
    return eq_curve


def calc_metrics(eq_curve):
    start_val = eq_curve[0][1]
    end_val = eq_curve[-1][1]
    days = (eq_curve[-1][0] - eq_curve[0][0]).days
    years = days / 365.0
    annual_ret = (end_val / start_val) ** (1/years) - 1
    # per step returns for sharpe
    rets = []
    for i in range(1, len(eq_curve)):
        r = eq_curve[i][1] / eq_curve[i-1][1] - 1
        rets.append(r)
    if rets:
        import math
        avg = sum(rets) / len(rets)
        std = (sum((x-avg)**2 for x in rets) / (len(rets)-1)) ** 0.5
        sharpe = (avg / std) * math.sqrt(6552) if std != 0 else 0
    else:
        sharpe = 0
    # max drawdown
    max_equity = eq_curve[0][1]
    max_dd = 0
    for _, eq in eq_curve:
        if eq > max_equity:
            max_equity = eq
        dd = (max_equity - eq) / max_equity
        if dd > max_dd:
            max_dd = dd
    mar = annual_ret / max_dd if max_dd != 0 else 0
    return annual_ret, sharpe, max_dd, mar


def monthly_win_rate(eq_curve):
    by_month = {}
    for dt, eq in eq_curve:
        key = (dt.year, dt.month)
        by_month.setdefault(key, [eq, eq])
        by_month[key][1] = eq
    wins = 0
    for (y, m), (start, end) in by_month.items():
        if end > start:
            wins += 1
    return wins / len(by_month)


def trade_frequency(trades):
    if not trades:
        return 0.0
    months = (trades[-1].exit_time - trades[0].time).days / 30.0
    return len(trades) / months if months else len(trades)


def main():
    import sys
    global SHORT_WINDOW, LONG_WINDOW, DATA_FILE
    if len(sys.argv) >= 3:
        SHORT_WINDOW = int(sys.argv[1])
        LONG_WINDOW = int(sys.argv[2])
    if len(sys.argv) >= 4:
        DATA_FILE = sys.argv[3]
    rows = read_data(DATA_FILE)
    eq_curve, trades = run_strategy(rows)
    bh_curve = buy_and_hold(rows)
    strat_metrics = calc_metrics(eq_curve)
    bh_metrics = calc_metrics(bh_curve)
    win_rate = monthly_win_rate(eq_curve)
    freq = trade_frequency(trades)
    print('Strategy performance:')
    print('Annualized Return: {:.2%}'.format(strat_metrics[0]))
    print('Sharpe Ratio: {:.2f}'.format(strat_metrics[1]))
    print('Max Drawdown: {:.2%}'.format(strat_metrics[2]))
    print('MAR Ratio: {:.2f}'.format(strat_metrics[3]))
    print('Monthly Win Rate: {:.2%}'.format(win_rate))
    print('Trade Frequency (per month): {:.2f}'.format(freq))
    print('\nBuy and Hold performance:')
    print('Annualized Return: {:.2%}'.format(bh_metrics[0]))
    print('Sharpe Ratio: {:.2f}'.format(bh_metrics[1]))
    print('Max Drawdown: {:.2%}'.format(bh_metrics[2]))
    print('MAR Ratio: {:.2f}'.format(bh_metrics[3]))

    # print first few trades
    print('\nSample trades (first 5):')
    for t in trades[:5]:
        print('Entry', t.time, 'price', t.price, 'exit', t.exit_time, 'price', t.exit_price, 'pos', t.position)

if __name__ == '__main__':
    main()
