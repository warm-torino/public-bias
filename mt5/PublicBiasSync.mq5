//+------------------------------------------------------------------+
//| PublicBiasSync.mq5  (Expert Advisor)                             |
//| GitHub 上の CSV を定期ダウンロードして                            |
//| MT5 共通フォルダ\Files\PublicBias\ に保存する。                    |
//| ※ WebRequest はインジケーターから呼べないため EA として分離。      |
//| ※ 売買は一切行わない。どのチャートでも 1 枚に入れれば OK。          |
//+------------------------------------------------------------------+
#property copyright "self-made"
#property version   "1.00"

input string InpBaseUrl     = "https://raw.githubusercontent.com/YOUR_NAME/publicbias/main/data/"; // CSV の置き場所（末尾 / 必須）
input string InpSymbols     = "EURUSD,GBPUSD,AUDUSD,USDJPY,EURJPY,GBPJPY,EURAUD,XAUUSD";        // 取得するシンボル
input int    InpIntervalMin = 10;            // 取得間隔（分）
input string InpFolder      = "PublicBias";  // 保存先（共通フォルダ内）
input string InpToken       = "";            // private リポジトリの場合のみ GitHub トークン

datetime g_last = 0;

//+------------------------------------------------------------------+
bool Download(const string sym)
  {
   string url = InpBaseUrl + sym + ".csv";
   string headers = (InpToken != "") ? "Authorization: token " + InpToken + "\r\n" : "";
   char   post[], result[];
   string resHeaders;

   ResetLastError();
   int code = WebRequest("GET", url, headers, 15000, post, result, resHeaders);
   if(code == -1)
     {
      int e = GetLastError();
      if(e == 4014)
         Print("WebRequest が許可されていません：ツール→オプション→エキスパートアドバイザに https://raw.githubusercontent.com を追加してください");
      else
         Print(sym, ": WebRequest エラー ", e);
      return false;
     }
   if(code != 200)       { Print(sym, ": HTTP ", code, "  ", url); return false; }
   if(ArraySize(result) < 20) { Print(sym, ": 内容が空"); return false; }

   string tmp = InpFolder + "\\" + sym + ".tmp";
   string dst = InpFolder + "\\" + sym + ".csv";
   int h = FileOpen(tmp, FILE_WRITE | FILE_BIN | FILE_COMMON);
   if(h == INVALID_HANDLE) { Print(sym, ": 一時ファイル作成失敗 ", GetLastError()); return false; }
   FileWriteArray(h, result);
   FileClose(h);

   if(!FileMove(tmp, FILE_COMMON, dst, FILE_COMMON | FILE_REWRITE))
     {
      Print(sym, ": 置き換え失敗 ", GetLastError());
      return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
void SyncAll()
  {
   g_last = TimeLocal();
   string syms[];
   int n = StringSplit(InpSymbols, ',', syms);
   int ok = 0, total = 0;
   for(int i = 0; i < n; i++)
     {
      string s = syms[i];
      StringTrimLeft(s);
      StringTrimRight(s);
      if(s == "") continue;
      total++;
      if(Download(s)) ok++;
     }
   Comment("PublicBiasSync: ", ok, "/", total, " 更新  ", TimeToString(TimeLocal(), TIME_DATE | TIME_MINUTES));
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   FolderCreate(InpFolder, FILE_COMMON);
   EventSetTimer(60);
   SyncAll();
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   Comment("");
  }

void OnTimer()
  {
   if(TimeLocal() - g_last >= InpIntervalMin * 60)
      SyncAll();
  }

void OnTick() {}
//+------------------------------------------------------------------+
