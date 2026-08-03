import { useEffect, useState } from "react";
import axios from "axios";


function App() {

  const [message, setMessage] = useState("");

  
  useEffect(() => {

  axios.get("/api/")
      .then((response) => {

        setMessage(response.data.message);

      })
      .catch((error)=>{

        console.log(error);

      });


  }, []);


  return (

    <div>

      <h1>
        Search & Savor
      </h1>


      <h2>
        Backend Response:
      </h2>


      <p>
        {message}
      </p>


    </div>

  );

}


export default App;