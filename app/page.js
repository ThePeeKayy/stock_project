"use client"
import { useEffect, useState } from "react"

const stockSymbols = [
  { symbol: "AAPL", name: "Apple" },
  { symbol: "MSFT", name: "Microsoft" },
  { symbol: "AMD", name: "Advanced Micro Devices" },
  { symbol: "NVDA", name: "NVIDIA" },
  { symbol: "TSLA", name: "Tesla" },
  { symbol: "CRM", name: "Salesforce" },
  { symbol: "SHOP", name: "Shopify" },
  { symbol: "GOOG", name: "Alphabet" },
]

function getCompanyDomain(symbol) {
  const domainMap = {
    AAPL: "apple.com",
    MSFT: "microsoft.com",
    AMD: "amd.com",
    NVDA: "nvidia.com",
    TSLA: "tesla.com",
    CRM: "salesforce.com",
    SHOP: "shopify.com",
    GOOG: "google.com",
  }
  return domainMap[symbol] || `${symbol.toLowerCase()}.com`
}

export default function StockBotHero() {
  const [currentIndex, setCurrentIndex] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentIndex((prevIndex) => (prevIndex + 1) % stockSymbols.length)
    }, 3000) // Rotate every 3 seconds

    return () => clearInterval(interval)
  }, [])

  return (
    <div className="relative min-h-screen flex items-center justify-center overflow-hidden">
      <div className="absolute inset-0 bg-[url('/grid.svg')] opacity-20"></div>
      
      <div className="relative z-10 max-w-6xl mx-auto px-4 text-center">
        <h1 className="text-5xl md:text-7xl font-bold text-black mb-6 tracking-tight">
          Predict Stock Market Trends with <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-blue-600">Stockly</span>
        </h1>

<div
        className=" absolute left-[calc(50%-4rem)] top-10 -z-10 transform-gpu blur-3xl sm:left-[calc(50%-18rem)] lg:left-48 lg:top-[calc(50%-30rem)] xl:left-[calc(50%-24rem)]"
        aria-hidden="true"
      >
        <div
          className="aspect-[1108/632] w-[69.25rem] bg-gradient-to-r from-[#80caff] to-[#4f46e5] opacity-20"
          style={{
            clipPath:
              'polygon(73.6% 51.7%, 91.7% 11.8%, 100% 46.4%, 97.4% 82.2%, 92.5% 84.9%, 75.7% 64%, 55.3% 47.5%, 46.5% 49.4%, 45% 62.9%, 50.3% 87.2%, 21.3% 64.1%, 0.1% 100%, 5.4% 51.1%, 21.4% 63.9%, 58.9% 0.2%, 73.6% 51.7%)',
          }}
        />
      </div>

        <div className="flex flex-wrap justify-center gap-4 mt-16">
          {stockSymbols.map((stock, index) => {
            const isActive = index === currentIndex
            return (
              <a
                key={stock.symbol}
                href={`/analysis/${stock.symbol}`}
                className={`
                  transition-all duration-500 ease-in-out
                  ${isActive 
                    ? "scale-110 opacity-100 shadow-xl shadow-blue-300/100" 
                    : "scale-100 opacity-60 hover:opacity-80"
                  }
                  bg-white/10 backdrop-blur-lg rounded-xl p-6 border border-gray/20
                  min-w-[160px] cursor-pointer
                `}
              >
                <div className="flex flex-col items-center gap-3">
                  <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center p-2 ">
                    <img 
                      src={`https://logo.clearbit.com/${getCompanyDomain(stock.symbol)}`}
                      alt={`${stock.name} logo`}
                      className="w-full h-full object-contain"
                      onError={(e) => {
                        // Fallback to alternative logo service if Clearbit fails
                        e.currentTarget.src = `https://img.logo.dev/${getCompanyDomain(stock.symbol)}?token=pk_X-NzA5MjQxOTI4OQ`
                      }}
                    />
                  </div>
                  <div className="text-2xl font-bold text-black">{stock.symbol}</div>
                  <div className="text-sm text-gray-700">{stock.name}</div>
                </div>
              </a>
            )
          })}
        </div>
      </div>
    </div>
  )
}