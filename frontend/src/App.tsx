import { useState } from "react";
import axios from "axios";

interface Video {
  title: string;
  channel: string;
  thumbnail: string;
  views: number;
  video_url: string;
}

function App() {
  const [dish, setDish] = useState("");
  const [language, setLanguage] = useState("Kannada");
  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(false);

  const searchRecipes = async () => {
    if (!dish.trim()) {
      alert("Please enter a dish name");
      return;
    }

    try {
      setLoading(true);

      const response = await axios.get("/api/search", {
        params: {
          dish,
          language,
        },
      });

      setVideos(response.data);
    } catch (error) {
      console.error(error);
      alert("Failed to fetch recipes");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: "2rem", maxWidth: "1200px", margin: "auto" }}>
      <h1>🍲 Search & Savor</h1>

      <p>
        Find the most popular recipe videos by dish and language.
      </p>

      <div style={{ display: "flex", gap: "1rem", marginBottom: "2rem" }}>
        <input
          type="text"
          placeholder="Enter dish name"
          value={dish}
          onChange={(e) => setDish(e.target.value)}
          style={{
            padding: "0.75rem",
            flex: 1,
          }}
        />

        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          style={{
            padding: "0.75rem",
          }}
        >
          <option>Kannada</option>
          <option>Tamil</option>
          <option>Telugu</option>
          <option>Hindi</option>
          <option>Malayalam</option>
          <option>English</option>
        </select>

        <button
          onClick={searchRecipes}
          disabled={loading}
        >
          {loading ? "Searching..." : "Search"}
        </button>
      </div>

      <div>
        {videos.map((video) => (
          <div
            key={video.video_url}
            style={{
              display: "flex",
              gap: "1rem",
              marginBottom: "1.5rem",
              border: "1px solid #ddd",
              padding: "1rem",
              borderRadius: "8px",
            }}
          >
            <img
              src={video.thumbnail}
              alt={video.title}
              width="220"
            />

            <div>
              <h3>{video.title}</h3>

              <p>
                <strong>Channel:</strong> {video.channel}
              </p>

              <p>
                <strong>Views:</strong>{" "}
                {video.views.toLocaleString()}
              </p>

              <a
                href={video.video_url}
                target="_blank"
                rel="noreferrer"
              >
                Watch on YouTube
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;