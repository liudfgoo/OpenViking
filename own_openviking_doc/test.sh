curl https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal \
   -H "Content-Type: application/json" \
   -H "Authorization: Bearer 478abbd2-724b-40b5-9226-27a562a76eda" \
   -d '{
    "model": "doubao-embedding-vision-251215",
    "input": [
        {
            "type":"text",
            "text":"天很蓝，海很深"
        },
        {    
            "type":"image_url",
            "image_url":{
                "url":"https://ark-project.tos-cn-beijing.volces.com/images/view.jpeg"
            }
        }
      ]
}'