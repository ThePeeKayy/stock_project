from flask import Flask, request, jsonify
import torch
import os
os.environ['CUDA_VISIBLE_DEVICES'] = ''
torch.cuda.is_available = lambda: False
from flask_cors import CORS
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pytorch_forecasting import TimeSeriesDataSet, NBeats, TemporalFusionTransformer
from pytorch_forecasting.data.encoders import GroupNormalizer
from pytorch_forecasting.metrics import QuantileLoss
import requests
import warnings
import pickle

from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

device = torch.device('cpu')

openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


SENTIMENT_API_URL = "https://api-inference.huggingface.co/models/cardiffnlp/twitter-roberta-base-sentiment"
warnings.filterwarnings('ignore')

app = Flask(__name__)
CORS(app)

# Global variables for loaded models
tft_model = None
training_dataset = None
nbeats_model = None

def load_models():
    """Load models at app startup using working method"""
    global tft_model, training_dataset, nbeats_model
    
    tft_model_path = "./tft_model-epoch=16-val_loss=9.4569.ckpt"
    training_path = './training_tft_model.pkl'
    
    if os.path.exists(tft_model_path) and os.path.exists(training_path):
        try:
            with open(training_path, 'rb') as f:
                training_dataset = pickle.load(f)
            
            checkpoint = torch.load(tft_model_path, map_location='cpu')
            
            tft_model = TemporalFusionTransformer.from_dataset(
                training_dataset,
                learning_rate=0.0005,
                hidden_size=8,
                attention_head_size=2,
                dropout=0.2,
                hidden_continuous_size=4,
                output_size=5,
                loss=QuantileLoss(quantiles=[0.1, 0.25, 0.5, 0.75, 0.9]),
                reduce_on_plateau_patience=4,
                optimizer="AdamW",
            )
            
            # Load the state dict from checkpoint
            tft_model.load_state_dict(checkpoint['state_dict'])
            tft_model.eval()
            tft_model = tft_model.cpu()
            
            print("TFT model loaded successfully")
        except Exception as e:
            print(f"Error loading TFT model: {e}")
            tft_model = None
            training_dataset = None
    
    nbeats_model_path = "./nbeats_model-epoch=14-val_loss=9.7598.ckpt"
    if os.path.exists(nbeats_model_path):
        try:
            nbeats_model = NBeats.load_from_checkpoint(nbeats_model_path, map_location='cpu')
            nbeats_model.eval()
            nbeats_model = nbeats_model.cpu()
            print("NBeats model loaded successfully")
        except Exception as e:
            print(f"Error loading NBeats model: {e}")
            nbeats_model = None

def compute_indicators(df):
    df['SMA_20'] = df['value'].rolling(20, min_periods=1).mean()
    delta = df['value'].diff()
    gain = delta.where(delta > 0, 0).rolling(14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=1).mean()
    rs = gain / loss.replace(0, np.inf)
    df['RSI'] = 100 - (100 / (1 + rs))
    df['MACD'] = df['value'].ewm(12).mean() - df['value'].ewm(26).mean()
    df['Volume_Ratio'] = df.get('Volume', pd.Series(1, index=df.index)) / df.get('Volume', pd.Series(1, index=df.index)).rolling(10).mean()
    return df.ffill().bfill()

def fetch_data(fred_key):
    import yfinance as yf
    
    def fetch_fred_data(series_id, start_date, end_date):
        url = f"https://api.stlouisfed.org/fred/series/observations"
        params = {'series_id': series_id, 'api_key': fred_key, 'file_type': 'json',
                 'observation_start': start_date.strftime('%Y-%m-%d'),
                 'observation_end': end_date.strftime('%Y-%m-%d')}
        response = requests.get(url, params=params, timeout=10).json()
        df = pd.DataFrame(response['observations'])
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        return df['value'].dropna().rename(series_id)

    def fetch_yfinance_data(symbol):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=18*30)
        ticker = yf.Ticker(symbol)
        data = ticker.history(start=start_date, end=end_date)
        return data['Close'].resample('MS').first().rename(symbol)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=18*30)
    combined_data = pd.DataFrame()

    for series_id in ['GDP', 'CPIAUCSL']:
        fred_series = fetch_fred_data(series_id, start_date, end_date)
        combined_data = pd.concat([combined_data, fred_series], axis=1)

    spy_data = fetch_yfinance_data('SPY')
    combined_data = pd.concat([combined_data, spy_data], axis=1)
    
    combined_data.reset_index(inplace=True)
    combined_data.rename(columns={'index': 'date'}, inplace=True)
    combined_data['date'] = pd.to_datetime(combined_data['date'], utc=True).dt.tz_localize(None)
    combined_data['date'] = combined_data['date'].dt.strftime('%Y-%m-%d')
    return combined_data.fillna(method='ffill').fillna(method='bfill')

def transform_polygon_data(raw_data):
    df = pd.DataFrame(raw_data)
    column_mapping = {'t': 'date', 'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'value', 'v': 'Volume'}
    df = df.rename(columns=column_mapping)
    df['date'] = pd.to_datetime(df['date'], unit='ms').dt.normalize()
    df['date'] = df['date'].dt.strftime('%Y-%m-%d')
    for col in ['date', 'Open', 'High', 'Low', 'value', 'Volume']:
        if col not in df.columns:
            df[col] = 0
    return df[['date', 'Open', 'High', 'Low', 'value', 'Volume']].to_dict('records')

def prepare_data(current_data, economic_data, symbol):
    current_df = pd.DataFrame(current_data)
    economic_df = pd.DataFrame(economic_data)
    
    current_df['date'] = pd.to_datetime(current_df['date']).dt.normalize()
    economic_df['date'] = pd.to_datetime(economic_df['date']).dt.normalize()
    current_df = current_df.sort_values('date').reset_index(drop=True)
    economic_df = economic_df.sort_values('date').reset_index(drop=True)
    
    merged = current_df.copy()
    
    if 'GDP' in economic_df.columns:
        gdp_data = economic_df[['date', 'GDP']].copy()
        gdp_data['gdp'] = gdp_data['GDP'] / 50
        merged = pd.merge_asof(merged, gdp_data[['date', 'gdp']], on='date', direction='backward')
    
    if 'CPIAUCSL' in economic_df.columns:
        cpi_data = economic_df[['date', 'CPIAUCSL']].rename(columns={'CPIAUCSL': 'cpi'})
        merged = pd.merge_asof(merged, cpi_data, on='date', direction='backward')
    
    if 'SPY' in economic_df.columns:
        spy_data = economic_df[['date', 'SPY']].rename(columns={'SPY': 'spy'})
        merged = pd.merge_asof(merged, spy_data, on='date', direction='backward')
    
    merged['month'] = merged['date'].dt.month.astype(str)
    merged['year'] = merged['date'].dt.year
    merged['group'] = symbol
    merged = compute_indicators(merged)
    merged['time_idx'] = np.arange(len(merged))
    
    return merged

def predict_tft(current_data, economic_data, symbol):
    """Fixed predict_tft function"""
    global tft_model, training_dataset
    
    try:
        if tft_model is None or training_dataset is None:
            return np.zeros(20)
        
        data = prepare_data(current_data, economic_data, symbol)
        recent_data = data.tail(100).copy()
        recent_data['time_idx'] = np.arange(len(recent_data))
        
        pred_dataset = TimeSeriesDataSet.from_dataset(training_dataset, recent_data, predict=True, stop_randomization=True)
        pred_loader = pred_dataset.to_dataloader(train=False, batch_size=1, num_workers=0)
        
        with torch.no_grad():
            predictions = tft_model.predict(pred_loader, mode='prediction')
        
        predictions = predictions.detach().cpu().numpy().squeeze()
        if predictions.ndim > 1 and predictions.shape[1] >= 5:
            predictions = predictions[:, 2]
        return predictions
        
    except Exception as e:
        print(f"TFT Error: {e}")
        return np.zeros(20)

def predict_nbeats(current_data, symbol):
    global nbeats_model
    
    try:
        if nbeats_model is None:
            return np.zeros(20)
        
        df = pd.DataFrame(current_data)
        df['date'] = pd.to_datetime(df['date']).dt.normalize()
        df = df.sort_values('date').reset_index(drop=True)
        df['time_idx'] = np.arange(len(df))
        df['group'] = symbol

        dataset = TimeSeriesDataSet(
            df, time_idx='time_idx', target='value', group_ids=['group'],
            min_encoder_length=80, max_encoder_length=80,
            min_prediction_length=20, max_prediction_length=20,
            time_varying_unknown_reals=['value'],
            target_normalizer=GroupNormalizer(groups=["group"], transformation=None, center=False),
            add_relative_time_idx=False,
        )
        
        forecast_dataset = TimeSeriesDataSet.from_dataset(dataset, df.iloc[-100:], predict=True, stop_randomization=True)
        forecast_dataloader = forecast_dataset.to_dataloader(train=False, batch_size=1, num_workers=0)
        forecasts = nbeats_model.predict(forecast_dataloader)
        
        return forecasts.cpu().numpy()[-1].flatten()
        
    except Exception as e:
        print(f"NBeats Error: {e}")
        return np.zeros(20)

@app.route('/predictor', methods=['POST'])
def predict():
    try:
        data = request.json
        symbol = data.get('symbol', 'AAPL').upper()
        current_data = transform_polygon_data(data.get('current_data'))
        economic_data = fetch_data(data.get('fred_key'))
        
        tft_pred = predict_tft(current_data, economic_data, symbol)
        nbeats_pred = predict_nbeats(current_data, symbol)
        
        last_date = pd.to_datetime(pd.DataFrame(current_data)['date'].max())
        tft_dates = pd.date_range(start=last_date, periods=len(tft_pred) + 1, freq='D')[1:]
        nbeats_dates = pd.date_range(start=last_date, periods=len(nbeats_pred) + 1, freq='D')[1:]
        
        all_data = []
        
        for _, row in pd.DataFrame(current_data).iterrows():
            all_data.append({'date': row['date'], 'value': float(row['value']), 'model': 'historical'})
        
        for i, pred in enumerate(tft_pred):
            all_data.append({'date': tft_dates[i].strftime('%Y-%m-%d'), 'value': float(pred), 'model': 'tft'})
        
        for i, pred in enumerate(nbeats_pred):
            all_data.append({'date': nbeats_dates[i].strftime('%Y-%m-%d'), 'value': float(pred), 'model': 'nbeats'})
        
        economic_json = pd.DataFrame(economic_data).to_json(orient='records')
        prediction_json = pd.DataFrame(all_data).to_json(orient='records')
        
        return jsonify([economic_json, prediction_json])
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

hf_headers = {
    "Authorization": f"Bearer {os.getenv('HF_API_KEY')}"
}


@app.route('/analyze', methods=['POST'])
def predict2():
    data = request.json
    text = data.get('news')
    symbol = data.get('stock')
    combined_text = f"For stock symbol {symbol}, {text}"

    sentiment_payload = {"inputs": combined_text}
    
    try:
        sentiment_response = requests.post(SENTIMENT_API_URL, headers=hf_headers, json=sentiment_payload)
        sentiment_response.raise_for_status()
        sentiment_result = sentiment_response.json()[0]
        sentiment = 'positive' if sentiment_result[0]['label'] == 'LABEL_2' else 'negative'
        print(f"Sentiment: {sentiment}")
    except Exception as e:
        print(f"Error during sentiment analysis: {e}")
        return jsonify({'error': str(e)})

    advice_prompt = (
        f"Stock Symbol: {symbol}\n"
        f"News Summary: {text}\n"
        f"Sentiment Analysis: {sentiment}\n\n"
        f"Based on the news and sentiment analysis, provide a detailed investment recommendation for {symbol}. "
        f"Should an investor buy, hold, or sell? Explain your reasoning in 2-3 sentences."
    )

    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": advice_prompt}],
            max_tokens=200,
            temperature=0.7
        )
        generated_advice = response.choices[0].message.content
    except Exception as e:
        print(f"Error during text generation: {e}")
        return jsonify({'error': str(e)})

    return jsonify({'sentiment': sentiment, 'advice': generated_advice})

@app.route('/health')
def health():
    return {"status": "healthy"}, 200

load_models()

if __name__ == '__main__':
    # Load models at startup
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)     