//+------------------------------------------------------------------+
//| PublicBias.mq5                                                   |
//| collector.py が書き出したリテール・ロング比率 CSV を               |
//| サブウィンドウに表示する（MT5 共通フォルダ\Files\PublicBias）      |
//+------------------------------------------------------------------+
#property copyright "self-made"
#property version   "1.00"
#property indicator_separate_window
#property indicator_buffers 1
#property indicator_plots   1
#property indicator_minimum 0
#property indicator_maximum 100
#property indicator_level1  50.0
#property indicator_level2  65.0
#property indicator_level3  35.0
#property indicator_levelcolor clrDimGray
#property indicator_levelstyle STYLE_DOT

#property indicator_label1  "Retail Long %"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrRed
#property indicator_style1  STYLE_SOLID
#property indicator_width1  2

input string InpSymbol            = "";           // CSVシンボル名（空=自動判定）
input string InpFolder            = "PublicBias"; // 共通フォルダ内のサブフォルダ
input int    InpReloadSec         = 60;           // CSV更新チェック間隔（秒）
input int    InpMaxGapHours       = 72;           // これより古いデータは表示しない（時間）
input int    InpServerOffsetHours = 99;           // サーバー時刻のUTC差（99=自動）

double   BufLong[];
datetime g_t[];
double   g_v[];
int      g_n         = 0;
string   g_sym       = "";
string   g_path      = "";
long     g_fileMod   = -1;
datetime g_lastCheck = 0;

//+------------------------------------------------------------------+
string AutoSymbol()
  {
   string s = _Symbol, out = "";
   for(int i = 0; i < StringLen(s); i++)
     {
      ushort c = StringGetCharacter(s, i);
      if((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9'))
         out += ShortToString(c);
     }
   StringToUpper(out);
   if(StringFind(out, "GOLD") == 0)   return "XAUUSD";
   if(StringFind(out, "SILVER") == 0) return "XAGUSD";
   if(StringLen(out) > 6) out = StringSubstr(out, 0, 6);   // EURUSDmicro → EURUSD
   return out;
  }

//+------------------------------------------------------------------+
int ServerOffsetSec()
  {
   if(InpServerOffsetHours != 99) return InpServerOffsetHours * 3600;
   long d = (long)(TimeTradeServer() - TimeGMT());
   return (int)(MathRound(d / 1800.0) * 1800);
  }

//+------------------------------------------------------------------+
//| t 以下で最も新しいレコードの添字（無ければ -1）                   |
//+------------------------------------------------------------------+
int FindIdx(datetime t)
  {
   int lo = 0, hi = g_n - 1, ans = -1;
   while(lo <= hi)
     {
      int mid = (lo + hi) / 2;
      if(g_t[mid] <= t) { ans = mid; lo = mid + 1; }
      else               hi = mid - 1;
     }
   return ans;
  }

//+------------------------------------------------------------------+
bool LoadCsv()
  {
   ResetLastError();
   long mod = FileGetInteger(g_path, FILE_MODIFY_DATE, true);
   if(mod < 0) { g_n = 0; g_fileMod = -1; return false; }

   int h = FileOpen(g_path, FILE_READ | FILE_CSV | FILE_ANSI | FILE_COMMON |
                    FILE_SHARE_READ | FILE_SHARE_WRITE, ',');
   if(h == INVALID_HANDLE) return false;

   // ヘッダー行を読み飛ばす
   do { FileReadString(h); } while(!FileIsLineEnding(h) && !FileIsEnding(h));

   int n = 0;
   ArrayResize(g_t, 0, 4096);
   ArrayResize(g_v, 0, 4096);
   while(!FileIsEnding(h))
     {
      string st = FileReadString(h);
      string sv = "";
      if(!FileIsLineEnding(h) && !FileIsEnding(h)) sv = FileReadString(h);
      while(!FileIsLineEnding(h) && !FileIsEnding(h)) FileReadString(h);   // 残りの列

      if(st == "" || sv == "") continue;
      datetime t = (datetime)StringToInteger(st);
      double   v = StringToDouble(sv);
      if(t <= 0 || v < 0.0 || v > 100.0) continue;
      if(n > 0 && t <= g_t[n - 1]) continue;                               // 重複・逆転は無視

      ArrayResize(g_t, n + 1, 4096);
      ArrayResize(g_v, n + 1, 4096);
      g_t[n] = t;
      g_v[n] = v;
      n++;
     }
   FileClose(h);
   g_n = n;
   g_fileMod = mod;
   return n > 0;
  }

//+------------------------------------------------------------------+
void UpdateName()
  {
   string s = "PublicBias " + g_sym;
   if(g_n == 0)
      s += "  (no data: Common\\Files\\" + g_path + ")";
   else
     {
      double last = g_v[g_n - 1];
      s += "  " + DoubleToString(last, 1) + "%";
      int k = FindIdx(g_t[g_n - 1] - 24 * 3600);
      if(k >= 0)
        {
         double d = last - g_v[k];
         s += " (24h " + (d >= 0 ? "+" : "") + DoubleToString(d, 1) + ")";
        }
      s += "  @" + TimeToString(g_t[g_n - 1] + ServerOffsetSec(), TIME_DATE | TIME_MINUTES);
     }
   IndicatorSetString(INDICATOR_SHORTNAME, s);
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   SetIndexBuffer(0, BufLong, INDICATOR_DATA);
   PlotIndexSetDouble(0, PLOT_EMPTY_VALUE, EMPTY_VALUE);
   IndicatorSetInteger(INDICATOR_DIGITS, 1);

   g_sym  = (InpSymbol == "") ? AutoSymbol() : InpSymbol;
   g_path = InpFolder + "\\" + g_sym + ".csv";
   LoadCsv();
   UpdateName();
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
  {
   bool reloaded = false;
   datetime now = TimeLocal();
   if(now - g_lastCheck >= InpReloadSec)
     {
      g_lastCheck = now;
      long mod = FileGetInteger(g_path, FILE_MODIFY_DATE, true);
      if(mod != g_fileMod)
        {
         LoadCsv();
         UpdateName();
         reloaded = true;
        }
     }

   ArraySetAsSeries(time, false);
   ArraySetAsSeries(BufLong, false);

   int start  = (prev_calculated > 0 && !reloaded) ? prev_calculated - 1 : 0;
   int off    = ServerOffsetSec();
   int ps     = PeriodSeconds(_Period);
   int maxGap = InpMaxGapHours * 3600;

   for(int i = start; i < rates_total; i++)
     {
      BufLong[i] = EMPTY_VALUE;
      if(g_n == 0) continue;
      datetime barEndUtc = time[i] - off + ps - 1;   // その足の終わり時点で判明していた値
      int k = FindIdx(barEndUtc);
      if(k < 0) continue;
      if(barEndUtc - g_t[k] > maxGap) continue;
      BufLong[i] = g_v[k];
     }
   return rates_total;
  }
//+------------------------------------------------------------------+
